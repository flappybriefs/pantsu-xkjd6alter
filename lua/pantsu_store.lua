local M = {}

M.version = "1"
M.index_version = "2"
M.override_file = "pantsu_overrides.tsv"
M.history_file = "pantsu_history.tsv"
M.undo_meta_file = "build/pantsu_undo.meta"
M.undo_override_file = "build/pantsu_undo.overrides.tsv"
M.undo_order_file = "build/pantsu_undo.order.tsv"
M.index_file = "build/pantsu_dictionary_index.tsv"
M.order_file = "pantsu_candidate_order.tsv"
M.dictionary_files = {
    "pantsu.core.dict.yaml",
    "pantsu.danzi.dict.yaml",
    "pantsu.cizu.dict.yaml",
    "pantsu.temp.dict.yaml",
    "pantsu.user.dict.yaml",
    "pantsu.waigua.dict.yaml",
}

M.overrides = nil
M.override_lookup = nil
M.index = nil
M.signature_cache = nil

local function data_path(path)
    if string.sub(path, 1, 1) == "/" then
        return path
    end
    if rime_api and rime_api.get_user_data_dir then
        return rime_api.get_user_data_dir() .. "/" .. path
    end
    return path
end

local function read_code_fields(line)
    return string.match(line, "^([^\t]+)\t([^\t%s]+)")
end

local function atomic_lines(path, lines)
    local target = data_path(path)
    local temp = target .. ".tmp"
    local file = io.open(temp, "w")
    if not file then
        return false
    end
    for _, line in ipairs(lines) do
        file:write(line, "\n")
    end
    if not file:close() then
        os.remove(temp)
        return false
    end
    if not os.rename(temp, target) then
        os.remove(temp)
        return false
    end
    return true
end

local function copy_file(source_path, target_path)
    local source = io.open(data_path(source_path), "rb")
    if not source then
        return atomic_lines(target_path, { "#missing" })
    end
    local content = source:read("*a")
    source:close()
    local target = io.open(data_path(target_path) .. ".tmp", "wb")
    if not target then
        return false
    end
    target:write(content)
    if not target:close() then
        return false
    end
    return os.rename(data_path(target_path) .. ".tmp", data_path(target_path))
end

local function restore_file(snapshot_path, target_path)
    local snapshot = io.open(data_path(snapshot_path), "rb")
    if not snapshot then
        return false
    end
    local content = snapshot:read("*a")
    snapshot:close()
    if content == "#missing\n" or content == "#missing" then
        os.remove(data_path(target_path))
        return true
    end
    local temp = data_path(target_path) .. ".tmp"
    local target = io.open(temp, "wb")
    if not target then
        return false
    end
    target:write(content)
    if not target:close() then
        return false
    end
    return os.rename(temp, data_path(target_path))
end

local function file_size(path)
    local file = io.open(data_path(path), "rb")
    if not file then
        return -1
    end
    local size = file:seek("end") or -1
    file:close()
    return size
end

local function file_fingerprint(path)
    local file = io.open(data_path(path), "rb")
    if not file then
        return "-1:0"
    end
    local size = file:seek("end") or 0
    local hash = 5381
    local positions = { 0 }
    if size > 4096 then
        table.insert(positions, math.floor(size / 2))
        table.insert(positions, math.max(0, size - 4096))
    end
    for _, position in ipairs(positions) do
        file:seek("set", position)
        local chunk = file:read(4096) or ""
        for index = 1, #chunk do
            hash = (hash * 33 + string.byte(chunk, index)) % 4294967296
        end
    end
    file:close()
    return tostring(size) .. ":" .. tostring(hash)
end

local function identity(path, line_number, word, base_code)
    return table.concat({
        path,
        tostring(line_number),
        word,
        base_code,
    }, ":")
end

function M.entry_id(path, line_number, word, base_code)
    return identity(path, line_number, word, base_code)
end

local function load_overrides()
    if M.overrides then
        return
    end
    M.overrides = {}
    M.override_lookup = {}
    local file = io.open(data_path(M.override_file), "r")
    if not file then
        return
    end
    for line in file:lines() do
        local fields = {}
        for value in string.gmatch(line, "[^\t]+") do
            table.insert(fields, value)
        end
        if fields[1] == "entry" and #fields >= 10 then
            M.overrides[fields[2]] = {
                id = fields[2],
                path = fields[3],
                line_number = tonumber(fields[4]),
                word = fields[5],
                base_code = fields[6],
                code = fields[7] == "-" and "" or fields[7],
                active = fields[8] == "1",
                updated = tonumber(fields[9]) or 0,
                device = fields[10],
            }
            local key = table.concat({
                fields[3], fields[5], fields[6],
            }, "\t")
            if not M.override_lookup[key] then
                M.override_lookup[key] = {}
            end
            table.insert(M.override_lookup[key], M.overrides[fields[2]])
        end
    end
    file:close()
end

local function find_override(id, path, line_number, word, base_code)
    local exact = M.overrides[id]
    if exact then
        return exact
    end
    local candidates = M.override_lookup[table.concat({
        path, word, base_code,
    }, "\t")] or {}
    local best
    for _, candidate in ipairs(candidates) do
        if not best
            or math.abs(candidate.line_number - line_number)
                < math.abs(best.line_number - line_number) then
            best = candidate
        end
    end
    return best
end

local function write_overrides()
    load_overrides()
    local entries = {}
    for _, entry in pairs(M.overrides) do
        table.insert(entries, entry)
    end
    table.sort(entries, function(left, right)
        return left.id < right.id
    end)
    local lines = { "version\t" .. M.index_version }
    for _, entry in ipairs(entries) do
        table.insert(lines, table.concat({
            "entry",
            entry.id,
            entry.path,
            tostring(entry.line_number),
            entry.word,
            entry.base_code,
            entry.code ~= "" and entry.code or "-",
            entry.active and "1" or "0",
            tostring(entry.updated),
            entry.device or "unknown",
        }, "\t"))
    end
    local ok = atomic_lines(M.override_file, lines)
    if ok then
        M.signature_cache = nil
        M.overrides = nil
        M.override_lookup = nil
    end
    return ok
end

local function build_index()
    local lines = { "version\t" .. M.version }
    local ranges = {}
    for _, path in ipairs(M.dictionary_files) do
        local size = file_size(path)
        table.insert(lines, table.concat({ "file", path, tostring(size) }, "\t"))
        local file = io.open(data_path(path), "rb")
        if file then
            local line_number = 0
            local current
            while true do
                local start = file:seek()
                local line = file:read("*l")
                if not line then
                    break
                end
                line_number = line_number + 1
                local _, code = read_code_fields(line)
                local prefix = code and string.sub(code, 1, math.min(2, #code))
                if prefix ~= current then
                    if current then
                        ranges[#ranges].finish = start
                    end
                    if prefix then
                        table.insert(ranges, {
                            path = path,
                            prefix = prefix,
                            start = start,
                            finish = size,
                            line_number = line_number,
                        })
                    end
                    current = prefix
                end
            end
            if current and ranges[#ranges] then
                ranges[#ranges].finish = size
            end
            file:close()
        end
    end
    for _, range in ipairs(ranges) do
        table.insert(lines, table.concat({
            "range",
            range.path,
            range.prefix,
            tostring(range.start),
            tostring(range.finish),
            tostring(range.line_number),
        }, "\t"))
    end
    if not atomic_lines(M.index_file, lines) then
        return nil
    end
    return ranges
end

local function load_index()
    if M.index then
        return M.index
    end
    local ranges = {}
    local valid = true
    local seen_files = {}
    local file = io.open(data_path(M.index_file), "r")
    if file then
        for line in file:lines() do
            local kind, a, b, c, d, e =
                string.match(line, "^([^\t]+)\t?([^\t]*)\t?([^\t]*)\t?([^\t]*)\t?([^\t]*)\t?(.*)$")
            if kind == "version" and a ~= M.index_version then
                valid = false
            elseif kind == "file" then
                seen_files[a] = true
                if tonumber(b) ~= file_size(a) then
                    valid = false
                end
            elseif kind == "range" then
                table.insert(ranges, {
                    path = a,
                    prefix = b,
                    start = tonumber(c),
                    finish = tonumber(d),
                    line_number = tonumber(e),
                })
            end
        end
        file:close()
    else
        valid = false
    end
    for _, path in ipairs(M.dictionary_files) do
        if not seen_files[path] then
            valid = false
        end
    end
    if not valid then
        ranges = build_index() or {}
    end
    M.index = ranges
    return ranges
end

function M.invalidate_index()
    M.index = nil
    M.signature_cache = nil
    os.remove(data_path(M.index_file))
end

function M.invalidate_signature()
    M.signature_cache = nil
end

local function range_matches(prefix, input)
    return string.sub(prefix, 1, #input) == input
        or string.sub(input, 1, #prefix) == prefix
end

function M.entries(input)
    load_overrides()
    local result = {}
    for _, range in ipairs(load_index()) do
        if range_matches(range.prefix, input) then
            local file = io.open(data_path(range.path), "rb")
            if file then
                file:seek("set", range.start)
                local line_number = range.line_number
                while (file:seek() or range.finish) < range.finish do
                    local line = file:read("*l")
                    if not line then
                        break
                    end
                    local word, base_code = read_code_fields(line)
                    if word and base_code then
                        local id = identity(
                            range.path, line_number, word, base_code)
                        local override = find_override(
                            id, range.path, line_number, word, base_code)
                        if override then
                            id = override.id
                        end
                        local code = override and override.code or base_code
                        local active = not override or override.active
                        if string.sub(base_code, 1, #input) == input
                            or (active and string.sub(code, 1, #input) == input) then
                            table.insert(result, {
                                id = id,
                                path = range.path,
                                line_number = line_number,
                                word = word,
                                base_code = base_code,
                                code = code,
                                original_code = code,
                                active = active,
                                initial_active = active,
                            })
                        end
                    end
                    line_number = line_number + 1
                end
                file:close()
            end
        end
    end
    return result
end

function M.override_roots()
    load_overrides()
    local roots = {}
    for _, entry in pairs(M.overrides) do
        for _, code in ipairs({ entry.base_code, entry.code }) do
            if code and code ~= "" then
                local length = math.min(4, #code)
                if length > 1 then
                    roots[string.sub(code, 1, length)] = true
                end
            end
        end
    end
    return roots
end

local function installation_id()
    local file = io.open(data_path("installation.yaml"), "r")
    if file then
        for line in file:lines() do
            local value = string.match(line, "^installation_id:%s*(.+)$")
            if value then
                file:close()
                return value
            end
        end
        file:close()
    end
    return "unknown"
end

local function append_history(action, input, word, details)
    M.rotate_log(M.history_file, 1048576)
    local file = io.open(data_path(M.history_file), "a")
    if not file then
        return
    end
    file:write(table.concat({
        tostring(os.time()),
        installation_id(),
        action,
        input or "-",
        word or "-",
        details or "-",
    }, "\t"), "\n")
    file:close()
end

function M.begin(action, input, word)
    if not copy_file(M.override_file, M.undo_override_file)
        or not copy_file(M.order_file, M.undo_order_file) then
        return false
    end
    return atomic_lines(M.undo_meta_file, {
        table.concat({
            tostring(os.time()),
            action,
            input or "-",
            word or "-",
        }, "\t"),
    })
end

function M.commit(entries, action, input, word)
    load_overrides()
    local changed = 0
    local now = os.time()
    local device = installation_id()
    for _, entry in ipairs(entries or {}) do
        if entry.active ~= entry.initial_active
            or entry.code ~= entry.original_code then
            changed = changed + 1
            if entry.active and entry.code == entry.base_code then
                M.overrides[entry.id] = nil
            else
                M.overrides[entry.id] = {
                    id = entry.id,
                    path = entry.path,
                    line_number = entry.line_number,
                    word = entry.word,
                    base_code = entry.base_code,
                    code = entry.active and entry.code or "",
                    active = entry.active,
                    updated = now,
                    device = device,
                }
            end
        end
    end
    if changed == 0 then
        return nil, "no_change"
    end
    if not write_overrides() then
        return nil, "override_write_failed"
    end
    append_history(action, input, word, tostring(changed))
    return true
end

function M.record_order(action, input, word)
    append_history(action, input, word, "same_code")
end

function M.signature()
    if M.signature_cache then
        return M.signature_cache
    end
    local parts = { M.version }
    for _, path in ipairs(M.dictionary_files) do
        table.insert(parts, path .. ":" .. file_fingerprint(path))
    end
    table.insert(parts,
        M.override_file .. ":" .. file_fingerprint(M.override_file))
    table.insert(parts,
        M.order_file .. ":" .. file_fingerprint(M.order_file))
    M.signature_cache = table.concat(parts, "|")
    return M.signature_cache
end

function M.undo()
    local meta = io.open(data_path(M.undo_meta_file), "r")
    if not meta then
        return nil, "nothing_to_undo"
    end
    local description = meta:read("*l") or ""
    meta:close()
    if not restore_file(M.undo_override_file, M.override_file)
        or not restore_file(M.undo_order_file, M.order_file) then
        return nil, "undo_restore_failed"
    end
    os.remove(data_path(M.undo_meta_file))
    M.overrides = nil
    M.override_lookup = nil
    M.signature_cache = nil
    append_history("undo", "-", "-", description)
    return true
end

function M.last_history()
    local file = io.open(data_path(M.history_file), "r")
    if not file then
        return nil
    end
    local last
    for line in file:lines() do
        last = line
    end
    file:close()
    if not last then
        return nil
    end
    local _, _, action, input, word =
        string.match(last, "^([^\t]+)\t([^\t]+)\t([^\t]+)\t([^\t]+)\t([^\t]+)")
    local labels = {
        promote = "前移",
        demote = "后移",
        delete = "删除",
        undo = "撤销",
        make_word = "造词",
    }
    return table.concat({
        labels[action] or action or "操作",
        word or "",
        input or "",
    }, " ")
end

function M.rotate_log(path, max_bytes)
    local target = data_path(path)
    local file = io.open(target, "rb")
    if not file then
        return
    end
    local size = file:seek("end") or 0
    file:close()
    if size <= max_bytes then
        return
    end
    os.remove(target .. ".1")
    os.rename(target, target .. ".1")
end

return M
