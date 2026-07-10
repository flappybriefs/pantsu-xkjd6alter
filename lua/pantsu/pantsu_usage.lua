local store = require("pantsu.pantsu_store")

local M = {
    summary_file = store.userdata_file("pantsu_usage.tsv"),
    event_file = store.userdata_file("pantsu_usage_events.tsv"),
    compact_threshold = 256,
    max_words = 20000,
    minimum_count = 5,
    minimum_share = 0.65,
    minimum_lead = 2,
    compact_event_bytes = 262144,
}

local records = {}
local loaded = false
local event_count = 0
local session_event_count = 0
local local_device = "unknown"

local function data_path(path)
    if rime_api and rime_api.get_user_data_dir then
        return rime_api.get_user_data_dir() .. "/" .. path
    end
    return path
end

local function read_content(path)
    local file = io.open(data_path(path), "rb")
    if not file then
        return nil
    end
    local content = file:read("*a")
    file:close()
    return content
end

local function verified_write(path, content)
    local target = data_path(path)
    local temp = target .. ".tmp"
    local file = io.open(temp, "wb")
    if not file then
        return false
    end
    if not file:write(content) or not file:close() then
        os.remove(temp)
        return false
    end
    local renamed = os.rename and os.rename(temp, target)
    if not renamed then
        os.remove(temp)
        file = io.open(target, "wb")
        if not file then
            return false
        end
        if not file:write(content) or not file:close() then
            return false
        end
    end
    local check = io.open(target, "rb")
    if not check then
        return false
    end
    local written = check:read("*a")
    check:close()
    return written == content
end

local function installation_id()
    local content = read_content("installation.yaml") or ""
    return string.match(content, "\n?installation_id:%s*([^\r\n]+)")
        or "unknown"
end

local function safe_field(value)
    value = tostring(value or "")
    return value ~= ""
        and not string.find(value, "[\t\r\n]")
end

local function apply_record(word, device, count, updated)
    if not safe_field(word) or not safe_field(device) then
        return
    end
    count = tonumber(count) or 0
    updated = tonumber(updated) or 0
    if count < 0 then
        return
    end
    local devices = records[word]
    if not devices then
        devices = {}
        records[word] = devices
    end
    local current = devices[device]
    if not current or count > current.count
        or (count == current.count and updated > current.updated) then
        devices[device] = {
            count = count,
            updated = updated,
        }
    end
end

local function apply_delta(word, device, count, updated)
    if not safe_field(word) or not safe_field(device) then
        return
    end
    count = tonumber(count) or 0
    updated = tonumber(updated) or 0
    if count <= 0 then
        return
    end
    local devices = records[word]
    if not devices then
        devices = {}
        records[word] = devices
    end
    local current = devices[device] or {
        count = 0,
        updated = 0,
    }
    devices[device] = {
        count = current.count + count,
        updated = math.max(current.updated or 0, updated),
    }
end

local function load_file(path, row_kind)
    local content = read_content(path)
    if not content then
        return false
    end
    for line in string.gmatch(content, "[^\r\n]+") do
        local kind, word, device, count, updated =
            string.match(line, "^([^\t]+)\t([^\t]+)\t([^\t]+)\t(%d+)\t(%d+)$")
        if kind == row_kind then
            apply_record(word, device, count, updated)
            if row_kind == "event" then
                event_count = event_count + 1
            end
        elseif row_kind == "event" and kind == "delta" then
            apply_delta(word, device, count, updated)
            event_count = event_count + 1
        end
    end
    return true
end

local function ensure_file(path)
    if not store.ensure_userdata_file(path) then
        return false
    end
    if read_content(path) ~= nil then
        return true
    end
    return verified_write(path, "version\t1\n")
end

local function file_size(path)
    local file = io.open(data_path(path), "rb")
    if not file then
        return 0
    end
    local size = file:seek("end") or 0
    file:close()
    return size
end

function M.init()
    if loaded then
        return true
    end
    records = {}
    event_count = 0
    session_event_count = 0
    local_device = installation_id()
    ensure_file(M.summary_file)
    ensure_file(M.event_file)
    load_file(M.summary_file, "word")
    load_file(M.event_file, "event")
    loaded = true
    return true
end

local function ensure_runtime_light()
    if local_device == "unknown" then
        local_device = installation_id()
    end
    ensure_file(M.summary_file)
    ensure_file(M.event_file)
end

local function word_total(word)
    local total = 0
    local updated = 0
    for _, state in pairs(records[word] or {}) do
        total = total + state.count
        updated = math.max(updated, state.updated)
    end
    return total, updated
end

function M.count(word)
    M.init()
    return word_total(word)
end

local function retained_words()
    local words = {}
    for word in pairs(records) do
        local total, updated = word_total(word)
        table.insert(words, {
            word = word,
            total = total,
            updated = updated,
        })
    end
    if #words > M.max_words then
        table.sort(words, function(left, right)
            if left.total == right.total then
                if left.updated == right.updated then
                    return left.word < right.word
                end
                return left.updated > right.updated
            end
            return left.total > right.total
        end)
        while #words > M.max_words do
            records[table.remove(words).word] = nil
        end
    end
    table.sort(words, function(left, right)
        return left.word < right.word
    end)
    return words
end

function M.compact()
    M.init()
    local lines = { "version\t1" }
    for _, item in ipairs(retained_words()) do
        local devices = records[item.word]
        local names = {}
        for device in pairs(devices) do
            table.insert(names, device)
        end
        table.sort(names)
        for _, device in ipairs(names) do
            local state = devices[device]
            table.insert(lines, table.concat({
                "word",
                item.word,
                device,
                tostring(state.count),
                tostring(state.updated),
            }, "\t"))
        end
    end
    local summary = table.concat(lines, "\n") .. "\n"
    if not verified_write(M.summary_file, summary) then
        return false
    end
    if not verified_write(M.event_file, "version\t1\n") then
        return false
    end
    event_count = 0
    session_event_count = 0
    return true
end

local function append_event(line)
    local path = data_path(M.event_file)
    local file = io.open(path, "ab")
    if file then
        local ok = file:write(line)
        local closed = file:close()
        if ok and closed then
            return true
        end
    end
    local content = read_content(M.event_file) or "version\t1\n"
    return verified_write(M.event_file, content .. line)
end

function M.record_selection(word, input)
    ensure_runtime_light()
    local length = utf8.len(word or "") or 0
    if length < 2 or string.len(input or "") < 3
        or not safe_field(word) then
        return false
    end
    local now = os.time()
    local line = table.concat({
        "delta",
        word,
        local_device,
        "1",
        tostring(now),
    }, "\t") .. "\n"
    if not append_event(line) then
        return false
    end
    if loaded then
        apply_delta(word, local_device, 1, now)
        event_count = event_count + 1
    end
    session_event_count = session_event_count + 1
    if (loaded and event_count >= M.compact_threshold)
        or session_event_count >= M.compact_threshold
        or file_size(M.event_file) >= M.compact_event_bytes then
        M.compact()
    end
    return true
end

function M.capture_selection(context, key_event, page_size)
    if not context or not context:has_menu() or context.input == "" then
        return nil
    end
    local candidate = context:get_selected_candidate()
    local keycode = key_event and key_event.keycode
    page_size = page_size and page_size > 0 and page_size or 7
    if keycode and keycode >= 0x31 and keycode < 0x31 + page_size
        and not key_event:ctrl() and not key_event:alt()
        and not key_event:super() then
        local composition = context.composition
        local segment = composition and not composition:empty()
            and composition:back() or nil
        if segment and segment.get_candidate_at then
            local selected = segment.selected_index or 0
            local page_start =
                math.floor(selected / page_size) * page_size
            candidate = segment:get_candidate_at(
                page_start + keycode - 0x31)
        end
    end
    if not candidate or not safe_field(candidate.text) then
        return nil
    end
    return {
        word = candidate.text,
        input = context.input,
    }
end

function M.commit_matches(context, pending)
    if not pending then
        return false
    end
    if context and context.get_commit_text then
        local ok, text = pcall(
            function()
                return context:get_commit_text()
            end)
        if ok and text and text ~= "" then
            return text == pending.word
        end
    end
    return true
end

function M.choose_candidate(candidates)
    M.init()
    local seen_words = {}
    local scored = {}
    local total = 0
    for _, entry in ipairs(candidates or {}) do
        if seen_words[entry.word] then
            return nil
        end
        seen_words[entry.word] = true
        local count = word_total(entry.word)
        total = total + count
        table.insert(scored, {
            entry = entry,
            count = count,
        })
    end
    table.sort(scored, function(left, right)
        if left.count == right.count then
            return left.entry.word < right.entry.word
        end
        return left.count > right.count
    end)
    local winner = scored[1]
    local runner = scored[2]
    if not winner or winner.count < M.minimum_count
        or total == 0
        or winner.count / total < M.minimum_share
        or winner.count - (runner and runner.count or 0) < M.minimum_lead then
        return nil
    end
    return winner.entry
end

function M.reset_for_test()
    records = {}
    loaded = false
    event_count = 0
    session_event_count = 0
    local_device = "unknown"
end

return M
