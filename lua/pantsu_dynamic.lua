local store = require("pantsu_store")
local M = {}

M.state_version = "4"
M.state_file = "build/pantsu_dynamic_candidates.tsv"
M.order_file = "pantsu_candidate_order.tsv"
M.build_state_file = "user.yaml"
M.dictionary_files = {
    "pantsu.core.dict.yaml",
    "pantsu.danzi.dict.yaml",
    "pantsu.cizu.dict.yaml",
    "pantsu.temp.dict.yaml",
    "pantsu.user.dict.yaml",
    "pantsu.waigua.dict.yaml",
}

M.loaded = false
M.build_time = nil
M.roots = {}
M.orders = {}
M.orders_loaded = false
M.order_roots_loaded = false
M.override_roots_loaded = false
M.status = nil

local function data_path(path)
    if string.sub(path, 1, 1) == "/" then
        return path
    end
    if rime_api and rime_api.get_user_data_dir then
        return rime_api.get_user_data_dir() .. "/" .. path
    end
    return path
end

local function load_orders()
    if M.orders_loaded then
        return
    end
    store.ensure_runtime_files()
    M.orders_loaded = true
    M.orders = {}
    local file = io.open(data_path(M.order_file), "r")
    if not file then
        return
    end
    for line in file:lines() do
        local code, rank, word =
            string.match(line, "^([^\t]+)\t(%d+)\t(.+)$")
        if code and rank and word then
            if not M.orders[code] then
                M.orders[code] = {}
            end
            M.orders[code][word] = tonumber(rank)
        end
    end
    file:close()
end

local function write_orders()
    local target = data_path(M.order_file)
    local temp = target .. ".tmp"
    local lines = {}
    local file = io.open(temp, "w")
    if not file then
        return false
    end
    local codes = {}
    for code in pairs(M.orders) do
        table.insert(codes, code)
    end
    table.sort(codes)
    for _, code in ipairs(codes) do
        local words = {}
        for word, rank in pairs(M.orders[code]) do
            table.insert(words, { word = word, rank = rank })
        end
        table.sort(words, function(left, right)
            if left.rank == right.rank then
                return left.word < right.word
            end
            return left.rank < right.rank
        end)
        for _, item in ipairs(words) do
            table.insert(lines, table.concat({
                code, tostring(item.rank), item.word,
            }, "\t"))
        end
    end
    local content = #lines > 0 and table.concat(lines, "\n") .. "\n" or ""
    file:write(content)
    if not file:close() then
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
        file:write(content)
        if not file:close() then
            return false
        end
    end
    local check = io.open(target, "rb")
    if not check then
        return false
    end
    local saved = check:read("*a")
    check:close()
    if saved ~= content then
        return false
    end
    store.invalidate_signature()
    return true
end

local function read_build_time()
    local file = io.open(data_path(M.build_state_file), "r")
    if not file then
        return nil
    end
    for line in file:lines() do
        local value = string.match(line, "^%s*last_build_time:%s*(%d+)")
        if value then
            file:close()
            return value
        end
    end
    file:close()
    return nil
end

local function clear_memory()
    M.roots = {}
end

local function remove_state_file()
    os.remove(data_path(M.state_file))
end

local function load_state()
    if M.loaded then
        return
    end
    M.loaded = true
    M.build_time = read_build_time()
    clear_memory()

    local file = io.open(data_path(M.state_file), "r")
    if not file then
        return
    end

    local state_build
    local state_signature
    local state_version
    local valid = true
    for line in file:lines() do
        local kind, root, first, second =
            string.match(line, "^([^\t]+)\t([^\t]*)\t?([^\t]*)\t?(.*)$")
        if kind == "format" then
            state_version = root
        elseif kind == "signature" then
            state_signature = root
        elseif kind == "build" then
            state_build = root
        elseif kind == "root" and root ~= "" then
            M.roots[root] = { entries = {}, suppress = {}, deleted = {} }
        elseif kind == "suppress" and M.roots[root] and first ~= "" then
            M.roots[root].suppress[first] = true
        elseif kind == "deleted" and M.roots[root] and first ~= "" then
            M.roots[root].deleted[first] = true
            M.roots[root].suppress[first] = true
        elseif kind == "entry" and M.roots[root]
            and first ~= "" and second ~= "" then
            local word, code, id =
                string.match(second, "^([^\t]+)\t([^\t]+)\t?(.*)$")
            if word and code then
                table.insert(M.roots[root].entries, {
                    word = word,
                    code = code,
                    id = id ~= "" and id or nil,
                })
                M.roots[root].suppress[word] = true
            else
                valid = false
            end
        end
    end
    file:close()

    if state_version ~= M.state_version
        or state_build ~= M.build_time
        or state_signature ~= store.signature()
        or not valid then
        clear_memory()
        remove_state_file()
    end
end

local function write_state()
    local target = data_path(M.state_file)
    local temp = target .. ".tmp"
    local file = io.open(temp, "w")
    if not file then
        return false
    end
    file:write("format\t", M.state_version, "\n")
    file:write("build\t", M.build_time or "", "\n")
    file:write("signature\t", store.signature(), "\n")

    local roots = {}
    for root in pairs(M.roots) do
        table.insert(roots, root)
    end
    table.sort(roots)
    for _, root in ipairs(roots) do
        local state = M.roots[root]
        file:write("root\t", root, "\n")
        local suppressed = {}
        for word in pairs(state.suppress) do
            table.insert(suppressed, word)
        end
        table.sort(suppressed)
        for _, word in ipairs(suppressed) do
            file:write("suppress\t", root, "\t", word, "\n")
        end
        local deleted = {}
        for word in pairs(state.deleted or {}) do
            table.insert(deleted, word)
        end
        table.sort(deleted)
        for _, word in ipairs(deleted) do
            file:write("deleted\t", root, "\t", word, "\n")
        end
        for index, entry in ipairs(state.entries) do
            file:write("entry\t", root, "\t", tostring(index), "\t",
                entry.word, "\t", entry.code, "\t",
                entry.id or "", "\n")
        end
    end
    if not file:close() then
        os.remove(temp)
        return false
    end
    local temp_file = io.open(temp, "rb")
    local expected = temp_file and temp_file:read("*a") or nil
    if temp_file then
        temp_file:close()
    end
    local renamed = os.rename and os.rename(temp, target)
    if not renamed then
        os.remove(temp)
        if not expected then
            return false
        end
        file = io.open(target, "wb")
        if not file then
            return false
        end
        file:write(expected)
        if not file:close() then
            return false
        end
    end
    local check = io.open(target, "rb")
    if not check then
        return false
    end
    local content = check:read("*a")
    check:close()
    return content
        and string.match(content, "^format\t" .. M.state_version .. "\n")
        and string.find(
            content, "\nsignature\t" .. store.signature() .. "\n",
            1, true) ~= nil
end

local function ensure_current_build()
    load_state()
end

local function common_prefix(values)
    if #values == 0 then
        return nil
    end
    local prefix = values[1]
    for index = 2, #values do
        local value = values[index]
        local length = math.min(string.len(prefix), string.len(value))
        local matched = 0
        for position = 1, length do
            if string.sub(prefix, position, position)
                ~= string.sub(value, position, position) then
                break
            end
            matched = position
        end
        prefix = string.sub(prefix, 1, matched)
        if prefix == "" then
            return nil
        end
    end
    return prefix
end

local function snapshot_root(root, extra_suppress, deleted_words)
    for old_root in pairs(M.roots) do
        if string.sub(root, 1, string.len(old_root)) == old_root
            and string.len(old_root) < string.len(root) then
            root = old_root
        end
    end

    local overlapping = {}
    for old_root in pairs(M.roots) do
        if string.sub(old_root, 1, string.len(root)) == root
            or string.sub(root, 1, string.len(old_root)) == old_root then
            table.insert(overlapping, old_root)
        end
    end
    for _, old_root in ipairs(overlapping) do
        M.roots[old_root] = nil
    end

    local state = { entries = {}, suppress = {}, deleted = {} }
    local order = 0
    local valid_orders = {}
    local source_entries = store.entries(root)
    local has_user_entry = {}
    for _, entry in ipairs(source_entries) do
        if entry.active and entry.path == "pantsu.user.dict.yaml" then
            has_user_entry[entry.word] = true
        end
    end
    load_orders()
    for _, entry in ipairs(source_entries) do
        state.suppress[entry.word] = true
        if entry.active
            and (entry.path == "pantsu.user.dict.yaml"
                or not has_user_entry[entry.word])
            and string.sub(entry.code, 1, string.len(root)) == root then
            order = order + 1
            table.insert(state.entries, {
                word = entry.word,
                code = entry.code,
                order = order,
                id = entry.id,
            })
            if M.orders[entry.code] and M.orders[entry.code][entry.word] then
                if not valid_orders[entry.code] then
                    valid_orders[entry.code] = {}
                end
                valid_orders[entry.code][entry.word] =
                    M.orders[entry.code][entry.word]
            end
        end
    end
    for _, word in ipairs(extra_suppress or {}) do
        state.suppress[word] = true
    end
    table.sort(state.entries, function(left, right)
        if left.code == right.code then
            load_orders()
            local ranks = M.orders[left.code]
            local left_rank = ranks and ranks[left.word]
            local right_rank = ranks and ranks[right.word]
            if left_rank or right_rank then
                left_rank = left_rank or 1000000 + left.order
                right_rank = right_rank or 1000000 + right.order
                if left_rank ~= right_rank then
                    return left_rank < right_rank
                end
            end
            return left.order < right.order
        end
        return left.code < right.code
    end)
    local order_changed = false
    load_orders()
    for code, ranks in pairs(M.orders) do
        if string.sub(code, 1, string.len(root)) == root then
            local kept = valid_orders[code] or {}
            local old_count, new_count = 0, 0
            for _ in pairs(ranks) do old_count = old_count + 1 end
            for _ in pairs(kept) do new_count = new_count + 1 end
            if old_count ~= new_count then
                if new_count > 1 then
                    M.orders[code] = kept
                else
                    M.orders[code] = nil
                end
                order_changed = true
            end
        end
    end
    if order_changed then
        write_orders()
    end
    M.roots[root] = state
end

local function root_for_code(code)
    if string.len(code) > 4 then
        return string.sub(code, 1, 4)
    end
    if string.len(code) > 1 then
        return string.sub(code, 1, string.len(code) - 1)
    end
    return code
end

function M.set_same_code_order(code, words)
    ensure_current_build()
    load_orders()
    local ranks = {}
    for index, word in ipairs(words or {}) do
        ranks[word] = index
    end
    if not next(ranks) then
        return false
    end
    M.orders[code] = ranks
    if not write_orders() then
        M.orders = {}
        M.orders_loaded = false
        return false
    end
    snapshot_root(root_for_code(code), words)
    M.order_roots_loaded = true
    if not write_state() then
        M.invalidate()
        return false
    end
    return true
end

function M.get_same_code_order(code)
    load_orders()
    local ranks = M.orders[code] or {}
    local result = {}
    for word, rank in pairs(ranks) do
        table.insert(result, { word = word, rank = rank })
    end
    table.sort(result, function(left, right)
        return left.rank < right.rank
    end)
    local words = {}
    for _, item in ipairs(result) do
        table.insert(words, item.word)
    end
    return words
end

local function ensure_order_roots()
    if M.order_roots_loaded then
        return
    end
    M.order_roots_loaded = true
    load_orders()
    local roots = {}
    for code in pairs(M.orders) do
        roots[root_for_code(code)] = true
    end
    local changed = false
    for root in pairs(roots) do
        if not M.roots[root] then
            snapshot_root(root)
            changed = true
        end
    end
    if changed then
        write_state()
    end
end

local function ensure_override_roots()
    if M.override_roots_loaded then
        return
    end
    M.override_roots_loaded = true
    local changed = false
    for root in pairs(store.override_roots()) do
        snapshot_root(root)
        changed = true
    end
    for root in pairs(store.self_word_roots()) do
        snapshot_root(root)
        changed = true
    end
    if changed then
        write_state()
    end
end

function M.invalidate()
    M.loaded = false
    M.roots = {}
    M.orders = {}
    M.orders_loaded = false
    M.order_roots_loaded = false
    M.override_roots_loaded = false
    remove_state_file()
end

function M.set_status(input, message, kind)
    M.status = {
        input = input,
        message = message,
        kind = kind or "transient",
    }
end

function M.clear_status()
    M.status = nil
end

function M.status_kind()
    return M.status and M.status.kind or nil
end

function M.get_status(input)
    if M.status and M.status.input == input then
        return M.status.message
    end
    return nil
end

function M.refresh_codes(codes, suppressed_words, preferred_root, deleted_words)
    ensure_current_build()
    local clean_codes = {}
    for _, code in ipairs(codes or {}) do
        if code and code ~= "" and code ~= "<deleted>" then
            table.insert(clean_codes, code)
        end
    end
    local root = common_prefix(clean_codes)
    if not root then
        return false
    end
    if type(preferred_root) == "string" and preferred_root ~= "" then
        root = preferred_root
    elseif type(preferred_root) == "number"
        and string.len(root) > preferred_root then
        root = string.sub(root, 1, preferred_root)
    end
    snapshot_root(root, suppressed_words, deleted_words)
    return write_state()
end

function M.refresh_entries(entries, preferred_root)
    local codes = {}
    local words = {}
    local deleted = {}
    for _, entry in ipairs(entries or {}) do
        if not entry.active or entry.code ~= entry.original_code then
            table.insert(words, entry.word)
            table.insert(codes, entry.original_code)
            if entry.active then
                table.insert(codes, entry.code)
            else
                table.insert(deleted, entry.word)
            end
        end
    end
    return M.refresh_codes(codes, words, preferred_root, deleted)
end

function M.match(input)
    ensure_current_build()
    ensure_order_roots()
    ensure_override_roots()
    local best_root
    for root in pairs(M.roots) do
        if string.sub(input, 1, string.len(root)) == root
            and (not best_root or string.len(root) > string.len(best_root)) then
            best_root = root
        end
    end
    if not best_root then
        return nil
    end
    return M.roots[best_root], best_root
end

return M
