local M = {}

M.version = "2"
M.index_version = "3"
M.runtime_version = "2026-06-21.5"
M.override_file = "pantsu_overrides.tsv"
M.history_file = "pantsu_history.tsv"
M.self_word_file = "pantsu_self_words.tsv"
M.self_word_ops_file = "pantsu_self_words_ops.tsv"
M.self_word_dict_file = "pantsu.zzc.dict.yaml"
M.undo_dir = "build/pantsu_undo"
M.undo_fallback_dir = "build"
M.undo_runtime_dir = nil
M.undo_limit = 7
M.undo_kinds = { "overrides", "order", "self_words", "self_word_ops" }
M.index_file = "build/pantsu_dictionary_index.tsv"
M.index_dirty_file = "build/pantsu_dictionary_index.dirty"
M.order_file = "pantsu_candidate_order.tsv"
M.dictionary_files = {
    "pantsu.core.dict.yaml",
    "pantsu.danzi.dict.yaml",
    "pantsu.cizu.dict.yaml",
    "pantsu.user.dict.yaml",
    "pantsu.zzc.dict.yaml",
}

M.overrides = nil
M.override_lookup = nil
M.index = nil
M.index_by_prefix = nil
M.signature_cache = nil
M.self_words_cache = nil
M.self_words_by_root = nil
M.self_word_keys = nil
M.effective_roots = {}
M.effective_root_order = {}
M.effective_root_length = 4
M.effective_root_limit = 32
M.self_word_ops_compact_bytes = 524288
M.pending_memory = nil
M.runtime_files_ready = false
M.dirty_index_files = {}
M.index_dirty_loaded = false

local migrate_undo_files

local function data_path(path)
    if string.sub(path, 1, 1) == "/" then
        return path
    end
    if rime_api and rime_api.get_user_data_dir then
        return rime_api.get_user_data_dir() .. "/" .. path
    end
    return path
end

local function shell_quote(value)
    return "'" .. string.gsub(value, "'", "'\\''") .. "'"
end

local function is_windows()
    return package and package.config
        and string.sub(package.config, 1, 1) == "\\"
end

local function directory_writable(path)
    local probe = path .. "/.pantsu-write-test"
    local file = io.open(data_path(probe), "w")
    if not file then
        return false
    end
    file:close()
    os.remove(data_path(probe))
    return true
end

local function ensure_undo_directory()
    if M.undo_runtime_dir then
        return M.undo_runtime_dir
    end
    if not directory_writable(M.undo_dir)
        and os.execute
        and not is_windows() then
        pcall(os.execute,
            "mkdir -p " .. shell_quote(data_path(M.undo_dir)))
    end
    if directory_writable(M.undo_dir) then
        M.undo_runtime_dir = M.undo_dir
    elseif directory_writable(M.undo_fallback_dir) then
        M.undo_runtime_dir = M.undo_fallback_dir
    end
    return M.undo_runtime_dir
end

local function undo_path(name)
    local directory = ensure_undo_directory()
    if not directory then
        return nil
    end
    if directory == M.undo_fallback_dir then
        return directory .. "/pantsu_undo." .. name
    end
    return directory .. "/" .. name
end

local function pending_path(kind)
    return undo_path("pending." .. kind .. ".tsv")
end

local function meta_path()
    return undo_path("pending.meta")
end

local function history_path()
    return undo_path("history.tsv")
end

local function read_code_fields(line)
    return string.match(line, "^([^\t]+)\t([^\t%s]+)")
end

local function verified_write(target, content, temp_suffix)
    local temp = target .. (temp_suffix or ".tmp")
    local file = io.open(temp, "w")
    if not file then
        return false
    end
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
    return saved == content
end

local function atomic_lines(path, lines)
    local content = #lines > 0 and table.concat(lines, "\n") .. "\n" or ""
    return verified_write(data_path(path), content)
end

local function read_last_build_time()
    local file = io.open(data_path("user.yaml"), "r")
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

local function load_dirty_index_files()
    if M.index_dirty_loaded then
        return
    end
    M.index_dirty_loaded = true
    local file = io.open(data_path(M.index_dirty_file), "r")
    if not file then
        return
    end
    for line in file:lines() do
        if line ~= "" then
            M.dirty_index_files[line] = true
        end
    end
    file:close()
end

local function write_dirty_index_files()
    local paths = {}
    for path in pairs(M.dirty_index_files) do
        table.insert(paths, path)
    end
    table.sort(paths)
    if #paths == 0 then
        os.remove(data_path(M.index_dirty_file))
        return true
    end
    return atomic_lines(M.index_dirty_file, paths)
end

local function ensure_runtime_marker()
    local path = data_path(M.override_file)
    local lines = {}
    local found = false
    local runtime_count = 0
    local file = io.open(path, "r")
    if file then
        for line in file:lines() do
            if string.match(line, "^runtime\t") then
                runtime_count = runtime_count + 1
                if line == "runtime\t" .. M.runtime_version then
                    found = true
                end
            else
                table.insert(lines, line)
            end
        end
        file:close()
    end
    if found and runtime_count == 1 then
        return true
    end
    table.insert(lines, 2, "runtime\t" .. M.runtime_version)
    return atomic_lines(M.override_file, lines)
end

local function ensure_file(path, initial_lines)
    local existing = io.open(data_path(path), "rb")
    if existing then
        existing:close()
        return true
    end
    return atomic_lines(path, initial_lines)
end

function M.ensure_runtime_files()
    if M.runtime_files_ready then
        return true
    end
    local ok = true
    if not ensure_file(M.override_file, {
        "version\t" .. M.index_version,
    }) then
        ok = false
    elseif not ensure_runtime_marker() then
        ok = false
    end
    if not ensure_file(M.history_file, {}) then
        ok = false
    end
    if not ensure_file(M.order_file, {}) then
        ok = false
    end
    if not ensure_file(M.self_word_file, { "version\t1" }) then
        ok = false
    end
    if not ensure_file(M.self_word_ops_file, { "version\t1" }) then
        ok = false
    end
    if migrate_undo_files and migrate_undo_files() then
        local undo_history = history_path()
        if undo_history then
            ensure_file(undo_history, {})
        end
    end
    M.runtime_files_ready = ok
    return ok
end

local function copy_file(source_path, target_path)
    local source = io.open(data_path(source_path), "rb")
    if not source then
        return atomic_lines(target_path, { "#missing" })
    end
    local content = source:read("*a")
    source:close()
    return verified_write(data_path(target_path), content)
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
    return verified_write(data_path(target_path), content)
end

local function capture_file(path)
    local file = io.open(data_path(path), "rb")
    if not file then
        return { missing = true }
    end
    local content = file:read("*a")
    file:close()
    return { content = content }
end

local function restore_capture(snapshot, target_path)
    if not snapshot or snapshot.missing then
        os.remove(data_path(target_path))
        return true
    end
    return verified_write(
        data_path(target_path), snapshot.content or "")
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
    M.ensure_runtime_files()
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

local function rebuild_self_word_buckets()
    M.self_words_by_root = {}
    for _, record in pairs(M.self_words_cache or {}) do
        if record.active and record.code ~= "" then
            for length = 2, math.min(M.effective_root_length, #record.code) do
                local root = string.sub(record.code, 1, length)
                if not M.self_words_by_root[root] then
                    M.self_words_by_root[root] = {}
                end
                table.insert(M.self_words_by_root[root], record)
            end
        end
    end
end

local function clear_self_word_cache()
    M.self_words_cache = nil
    M.self_words_by_root = nil
    M.self_word_keys = nil
end

local function load_self_words()
    if M.self_words_cache then
        return
    end
    M.ensure_runtime_files()
    M.self_words_cache = {}
    M.self_word_keys = {}
    local seen_keys = {}
    local function load_file(path)
        local file = io.open(data_path(path), "r")
        if not file then
            return
        end
        for line in file:lines() do
            local kind, word, code, active, updated, device =
                string.match(line,
                    "^([^\t]+)\t([^\t]+)\t([^\t]+)\t([01])\t([^\t]+)\t(.*)$")
            if kind == "word" and word and code then
                updated = tonumber(updated) or 0
                local key = word .. "\t" .. code
                local old = M.self_words_cache[key]
                if not old or updated >= (old.updated or 0) then
                    M.self_words_cache[key] = {
                        word = word,
                        code = code,
                        active = active == "1",
                        updated = updated,
                        device = device ~= "" and device or "unknown",
                    }
                end
                seen_keys[key] = true
            end
        end
        file:close()
    end
    load_file(M.self_word_file)
    load_file(M.self_word_ops_file)
    for key in pairs(seen_keys) do
        table.insert(M.self_word_keys, key)
    end
    table.sort(M.self_word_keys)
    rebuild_self_word_buckets()
end

local function insert_self_word_key(key)
    local low, high = 1, #M.self_word_keys
    while low <= high do
        local middle = math.floor((low + high) / 2)
        if M.self_word_keys[middle] < key then
            low = middle + 1
        else
            high = middle - 1
        end
    end
    if M.self_word_keys[low] ~= key then
        table.insert(M.self_word_keys, low, key)
    end
end

local function write_self_words()
    load_self_words()
    local lines = { "version\t1" }
    for _, key in ipairs(M.self_word_keys) do
        local record = M.self_words_cache[key]
        if record then
            table.insert(lines, table.concat({
                "word",
                record.word,
                record.code,
                record.active and "1" or "0",
                tostring(record.updated or 0),
                record.device or "unknown",
            }, "\t"))
        end
    end
    local ok = atomic_lines(M.self_word_file, lines)
    if ok then
        M.signature_cache = nil
    end
    return ok
end

local function append_self_word_ops(records)
    local file = io.open(data_path(M.self_word_ops_file), "a")
    if not file then
        return false
    end
    for _, record in ipairs(records or {}) do
        file:write(table.concat({
            "word",
            record.word,
            record.code,
            record.active and "1" or "0",
            tostring(record.updated or 0),
            record.device or "unknown",
        }, "\t"), "\n")
    end
    return file:close()
end

local function compact_self_word_ops_if_needed()
    if file_size(M.self_word_ops_file) < M.self_word_ops_compact_bytes then
        return true
    end
    if not write_self_words() then
        return false
    end
    return atomic_lines(M.self_word_ops_file, { "version\t1" })
end

function M.self_word_candidates(input)
    load_self_words()
    if not input or #input < 2 then
        return M.self_words_cache
    end
    local root = string.sub(
        input, 1, math.min(M.effective_root_length, #input))
    return M.self_words_by_root[root] or {}
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
    local lines = {
        "version\t" .. M.index_version,
        "runtime\t" .. M.runtime_version,
    }
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
        M.override_lookup = {}
        for _, entry in pairs(M.overrides) do
            local key = table.concat({
                entry.path, entry.word, entry.base_code,
            }, "\t")
            if not M.override_lookup[key] then
                M.override_lookup[key] = {}
            end
            table.insert(M.override_lookup[key], entry)
        end
    end
    return ok
end

local function scan_file_ranges(path)
    local ranges = {}
    local size = file_size(path)
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
    return ranges
end

local function write_index(ranges)
    local lines = {
        "version\t" .. M.index_version,
        "build\t" .. (read_last_build_time() or ""),
    }
    for _, path in ipairs(M.dictionary_files) do
        table.insert(lines, table.concat({
            "file",
            path,
            tostring(file_size(path)),
            file_fingerprint(path),
        }, "\t"))
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
    M.dirty_index_files = {}
    M.index_dirty_loaded = true
    os.remove(data_path(M.index_dirty_file))
    return ranges
end

local function set_index(ranges)
    M.index = ranges
    M.index_by_prefix = {}
    for _, range in ipairs(ranges or {}) do
        if not M.index_by_prefix[range.prefix] then
            M.index_by_prefix[range.prefix] = {}
        end
        table.insert(M.index_by_prefix[range.prefix], range)
    end
    return ranges
end

local function load_index()
    if M.index then
        return M.index
    end
    local ranges = {}
    local by_file = {}
    local stored_sizes = {}
    local stored_fingerprints = {}
    local stored_build
    local version_valid = false
    local build_seen = false
    load_dirty_index_files()
    local file = io.open(data_path(M.index_file), "r")
    if file then
        for line in file:lines() do
            local kind, a, b, c, d, e =
                string.match(line, "^([^\t]+)\t?([^\t]*)\t?([^\t]*)\t?([^\t]*)\t?([^\t]*)\t?(.*)$")
            if kind == "version" then
                version_valid = a == M.index_version
            elseif kind == "build" then
                build_seen = true
                stored_build = a ~= "" and a or nil
            elseif kind == "file" then
                stored_sizes[a] = tonumber(b)
                stored_fingerprints[a] = c
            elseif kind == "range" then
                if not by_file[a] then
                    by_file[a] = {}
                end
                table.insert(by_file[a], {
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
        version_valid = false
    end
    local changed = false
    for _, path in ipairs(M.dictionary_files) do
        local reusable = version_valid
            and build_seen
            and not M.dirty_index_files[path]
            and stored_sizes[path] == file_size(path)
            and stored_fingerprints[path] == file_fingerprint(path)
            and by_file[path] ~= nil
        local file_ranges = reusable and by_file[path]
            or scan_file_ranges(path)
        if not reusable then
            changed = true
        end
        for _, range in ipairs(file_ranges or {}) do
            table.insert(ranges, range)
        end
    end
    if changed then
        ranges = write_index(ranges) or ranges
    end
    set_index(ranges)
    M.dirty_index_files = {}
    return ranges
end

function M.invalidate_index(path, codes)
    M.signature_cache = nil
    if codes then
        M.invalidate_effective_codes(codes)
    else
        M.invalidate_effective_index()
    end
    if path and M.index then
        local by_file = {}
        for _, range in ipairs(M.index) do
            if range.path ~= path then
                if not by_file[range.path] then
                    by_file[range.path] = {}
                end
                table.insert(by_file[range.path], range)
            end
        end
        by_file[path] = scan_file_ranges(path)
        local refreshed = {}
        for _, dictionary in ipairs(M.dictionary_files) do
            for _, range in ipairs(by_file[dictionary] or {}) do
                table.insert(refreshed, range)
            end
        end
        set_index(refreshed)
        load_dirty_index_files()
        M.dirty_index_files[path] = true
        if not write_dirty_index_files() then
            M.dirty_index_files = {}
            M.index_dirty_loaded = true
            os.remove(data_path(M.index_file))
        end
        return
    end
    M.index = nil
    M.index_by_prefix = nil
    if path then
        load_dirty_index_files()
        M.dirty_index_files[path] = true
        if not write_dirty_index_files() then
            M.dirty_index_files = {}
            M.index_dirty_loaded = true
            os.remove(data_path(M.index_file))
        end
    else
        M.dirty_index_files = {}
        M.index_dirty_loaded = true
        os.remove(data_path(M.index_file))
        os.remove(data_path(M.index_dirty_file))
    end
end

function M.invalidate_signature()
    M.signature_cache = nil
end

local function effective_root(code)
    if not code or code == "" then
        return nil
    end
    return string.sub(code, 1, math.min(M.effective_root_length, #code))
end

local function remove_effective_root(root)
    M.effective_roots[root] = nil
    for index = #M.effective_root_order, 1, -1 do
        if M.effective_root_order[index] == root then
            table.remove(M.effective_root_order, index)
        end
    end
end

local function touch_effective_root(root)
    for index = #M.effective_root_order, 1, -1 do
        if M.effective_root_order[index] == root then
            table.remove(M.effective_root_order, index)
            break
        end
    end
    table.insert(M.effective_root_order, root)
    while #M.effective_root_order > M.effective_root_limit do
        local expired = table.remove(M.effective_root_order, 1)
        M.effective_roots[expired] = nil
    end
end

function M.invalidate_effective_codes(codes)
    for _, code in ipairs(codes or {}) do
        if code and code ~= "" then
            for length = 2, math.min(M.effective_root_length, #code) do
                remove_effective_root(string.sub(code, 1, length))
            end
        end
    end
end

function M.invalidate_effective_index()
    M.effective_roots = {}
    M.effective_root_order = {}
end

local function range_matches(prefix, input)
    return string.sub(prefix, 1, #input) == input
        or string.sub(input, 1, #prefix) == prefix
end

local function matching_ranges(input)
    local result = {}
    local current
    local ranges = load_index()
    if #input >= 2 then
        ranges = M.index_by_prefix[string.sub(input, 1, 2)] or {}
    end
    for _, range in ipairs(ranges) do
        if range_matches(range.prefix, input) then
            if current and current.path == range.path
                and current.finish == range.start then
                current.finish = range.finish
            else
                current = {
                    path = range.path,
                    start = range.start,
                    finish = range.finish,
                    line_number = range.line_number,
                }
                table.insert(result, current)
            end
        else
            current = nil
        end
    end
    return result
end

local function scan_entries(input, profile)
    load_overrides()
    if profile then
        profile:mark("overrides_load")
    end
    local result = {}
    local found_self = {}
    local ranges = matching_ranges(input)
    if profile and profile.count then
        profile:count("dictionary_range_count", #ranges)
    end
    for _, range in ipairs(ranges) do
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
                        if range.path == M.self_word_dict_file and active then
                            found_self[word .. "\t" .. code] = true
                        end
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
    if profile then
        profile:mark("dictionary_scan")
    end
    for _, record in pairs(M.self_word_candidates(input)) do
        local key = record.word .. "\t" .. record.code
        if record.active and not found_self[key]
            and string.sub(record.code, 1, #input) == input then
            local id = "self:" .. record.word .. ":" .. record.code
            local override = M.overrides[id]
            local code = override and override.code or record.code
            local active = not override or override.active
            if active and string.sub(code, 1, #input) == input then
                table.insert(result, {
                    id = id,
                    path = M.self_word_dict_file,
                    line_number = 0,
                    word = record.word,
                    base_code = record.code,
                    code = code,
                    original_code = code,
                    active = true,
                    initial_active = true,
                    virtual = true,
                })
            end
        end
    end
    if profile then
        profile:mark("self_words_merge")
    end
    return result
end

local function copy_entry(entry)
    return {
        id = entry.id,
        path = entry.path,
        line_number = entry.line_number,
        word = entry.word,
        base_code = entry.base_code,
        code = entry.code,
        original_code = entry.original_code,
        active = entry.active,
        initial_active = entry.initial_active,
        virtual = entry.virtual,
    }
end

local function entry_matches(entry, input)
    return string.sub(entry.base_code, 1, #input) == input
        or (entry.active and string.sub(entry.code, 1, #input) == input)
end

function M.entries(input, profile)
    if not input or #input < 2 then
        return scan_entries(input or "", profile)
    end
    local root = effective_root(input)
    local entries = M.effective_roots[root]
    if not entries then
        entries = scan_entries(root, profile)
        M.effective_roots[root] = entries
        if profile then
            profile:mark("effective_index_build")
        end
    elseif profile then
        profile:mark("effective_index_hit")
    end
    touch_effective_root(root)
    local result = {}
    for _, entry in ipairs(entries) do
        if entry_matches(entry, input) then
            table.insert(result, copy_entry(entry))
        end
    end
    return result
end

function M.occupied_prefixes(input, target_word, minimum, maximum, profile)
    local occupied = {}
    for _, entry in ipairs(M.entries(input, profile)) do
        if entry.active and entry.word ~= target_word
            and string.sub(entry.code, 1, #input) == input then
            local limit = math.min(maximum, #entry.code)
            for length = minimum, limit do
                occupied[string.sub(entry.code, 1, length)] = true
            end
        end
    end
    if profile then
        profile:mark("occupancy_scan")
    end
    return occupied
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

function M.self_word_roots()
    load_self_words()
    local roots = {}
    for _, record in pairs(M.self_words_cache) do
        if record.active and record.code ~= "" then
            local length = math.min(4, #record.code)
            if length > 1 then
                roots[string.sub(record.code, 1, length)] = true
            end
        end
    end
    return roots
end

function M.clear_word_overrides(path, word)
    load_overrides()
    local changed = false
    local affected_codes = {}
    for id, entry in pairs(M.overrides) do
        if entry.path == path and entry.word == word then
            table.insert(affected_codes, entry.base_code)
            table.insert(affected_codes, entry.code)
            M.overrides[id] = nil
            changed = true
        end
    end
    if changed and not write_overrides() then
        return nil, "override_write_failed"
    end
    if changed then
        M.invalidate_effective_codes(affected_codes)
    end
    return true, changed
end

function M.effective_entry(path, word, base_code)
    load_overrides()
    local candidates = M.override_lookup[table.concat({
        path, word, base_code,
    }, "\t")] or {}
    local override = candidates[1]
    if override then
        return override.active, override.code
    end
    return true, base_code
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

function M.self_words()
    load_self_words()
    local result = {}
    for key, record in pairs(M.self_words_cache) do
        result[key] = {
            word = record.word,
            code = record.code,
            active = record.active,
            updated = record.updated,
            device = record.device,
        }
    end
    return result
end

function M.has_self_word_records()
    load_self_words()
    return next(M.self_words_cache) ~= nil
end

function M.update_self_words(updates, only_missing)
    load_self_words()
    local changed = false
    local changed_records = {}
    local affected_codes = {}
    local now = os.time()
    local device = installation_id()
    for _, update in ipairs(updates or {}) do
        local key = update.word and update.code
            and update.word .. "\t" .. update.code or nil
        local old = key and M.self_words_cache[key] or nil
        if update.word and update.word ~= ""
            and update.code and update.code ~= ""
            and (not only_missing or not old) then
            local active = update.active ~= false
            if not old or old.active ~= active then
                if not old then
                    insert_self_word_key(key)
                end
                local record = {
                    word = update.word,
                    code = update.code,
                    active = active,
                    updated = update.updated or now,
                    device = update.device or device,
                }
                M.self_words_cache[key] = record
                table.insert(changed_records, record)
                table.insert(affected_codes, update.code)
                changed = true
            end
        end
    end
    if changed and not append_self_word_ops(changed_records) then
        clear_self_word_cache()
        return nil, "self_word_write_failed"
    end
    if changed then
        M.signature_cache = nil
        rebuild_self_word_buckets()
        M.invalidate_effective_codes(affected_codes)
        compact_self_word_ops_if_needed()
    end
    return true, changed
end

function M.replace_self_word(word, codes)
    load_self_words()
    local wanted = {}
    for _, code in ipairs(codes or {}) do
        if code and code ~= "" then
            wanted[code] = true
        end
    end
    local updates = {}
    for _, record in pairs(M.self_words_cache) do
        if record.word == word and record.active and not wanted[record.code] then
            table.insert(updates, {
                word = word,
                code = record.code,
                active = false,
            })
        end
    end
    for code in pairs(wanted) do
        table.insert(updates, {
            word = word,
            code = code,
            active = true,
        })
    end
    return M.update_self_words(updates)
end

local function append_history(action, input, word, details)
    M.ensure_runtime_files()
    local lines = {}
    local file = io.open(data_path(M.history_file), "r")
    if file then
        for line in file:lines() do
            if line ~= "" then
                table.insert(lines, line)
            end
        end
        file:close()
    end
    table.insert(lines, table.concat({
        tostring(os.time()),
        installation_id(),
        action,
        input or "-",
        word or "-",
        details or "-",
    }, "\t"))
    local total = 0
    for _, line in ipairs(lines) do
        total = total + #line + 1
    end
    while total > 1048576 and #lines > 1 do
        total = total - #lines[1] - 1
        table.remove(lines, 1)
    end
    return atomic_lines(M.history_file, lines)
end

local function snapshot_file(slot, kind)
    return undo_path(
        tostring(slot) .. "." .. kind .. ".tsv")
end

local function file_exists(path)
    if not path then
        return false
    end
    local file = io.open(data_path(path), "rb")
    if not file then
        return false
    end
    file:close()
    return true
end

local function migrate_file(source, destination)
    if not source or not destination or not file_exists(source) then
        return true
    end
    if file_exists(destination) then
        os.remove(data_path(source))
        return true
    end
    if os.rename
        and os.rename(data_path(source), data_path(destination)) then
        return true
    end
    if not copy_file(source, destination) then
        return false
    end
    os.remove(data_path(source))
    return true
end

migrate_undo_files = function()
    if not ensure_undo_directory() then
        return false
    end
    local ok = migrate_file(
        "pantsu_undo_history.tsv", history_path())
    for slot = 1, M.undo_limit do
        for _, kind in ipairs(M.undo_kinds) do
            ok = migrate_file(
                "pantsu_undo_" .. tostring(slot)
                    .. "." .. kind .. ".tsv",
                snapshot_file(slot, kind)) and ok
        end
    end
    for _, item in ipairs({
        { "build/pantsu_undo.meta", meta_path() },
        { "build/pantsu_undo.overrides.tsv",
            pending_path("overrides") },
        { "build/pantsu_undo.order.tsv",
            pending_path("order") },
        { "build/pantsu_undo.self_words.tsv",
            pending_path("self_words") },
        { "build/pantsu_undo.self_word_ops.tsv",
            pending_path("self_word_ops") },
    }) do
        ok = migrate_file(item[1], item[2]) and ok
    end
    return ok
end

local function remove_pending()
    for _, path in ipairs({
        meta_path(),
        pending_path("overrides"),
        pending_path("order"),
        pending_path("self_words"),
        pending_path("self_word_ops"),
    }) do
        if path then
            os.remove(data_path(path))
        end
    end
end

local function read_undo_lines()
    local lines = {}
    migrate_undo_files()
    local path = history_path()
    local file = path and io.open(data_path(path), "r")
    if file then
        for line in file:lines() do
            if line ~= "" then
                table.insert(lines, line)
            end
        end
        file:close()
    end
    return lines
end

function M.begin(action, input, word, profile)
    M.ensure_runtime_files()
    if profile then
        profile:mark("runtime_files")
    end
    M.pending_memory = {
        description = table.concat({
            tostring(os.time()),
            action,
            input or "-",
            word or "-",
        }, "\t"),
        overrides = capture_file(M.override_file),
        order = capture_file(M.order_file),
        self_words = capture_file(M.self_word_file),
        self_word_ops = capture_file(M.self_word_ops_file),
    }
    if profile then
        profile:mark("memory_snapshot")
    end
    if not migrate_undo_files() then
        if profile then
            profile:mark("undo_unavailable")
        end
        return true
    end
    remove_pending()
    if not copy_file(M.override_file, pending_path("overrides"))
        or not copy_file(M.order_file, pending_path("order"))
        or not copy_file(
            M.self_word_file, pending_path("self_words"))
        or not copy_file(
            M.self_word_ops_file, pending_path("self_word_ops")) then
        remove_pending()
        return true
    end
    local ok = atomic_lines(meta_path(), {
        table.concat({
            tostring(os.time()),
            action,
            input or "-",
            word or "-",
        }, "\t"),
    })
    if not ok then
        remove_pending()
        if profile then
            profile:mark("undo_memory_only")
        end
        return true
    end
    if profile then
        profile:mark("undo_pending")
    end
    return true
end

function M.finish(action, input, word, details, profile)
    local meta_file = meta_path()
    local meta = meta_file and io.open(data_path(meta_file), "r")
    if not meta then
        if not M.pending_memory then
            return nil, "backup_missing"
        end
        M.pending_memory = nil
        append_history(action, input, word, details or "-")
        if profile then
            profile:mark("operation_history")
        end
        return true
    end
    if profile then
        profile:mark("undo_rotate")
    end
    local description = meta:read("*l") or table.concat({
        tostring(os.time()), action, input or "-", word or "-",
    }, "\t")
    meta:close()

    for slot = M.undo_limit - 1, 1, -1 do
        for _, kind in ipairs(M.undo_kinds) do
            local source = snapshot_file(slot, kind)
            local destination = snapshot_file(slot + 1, kind)
            os.remove(data_path(destination))
            local source_file = io.open(data_path(source), "rb")
            if source_file then
                source_file:close()
                if not copy_file(source, destination) then
                    return nil, "backup_rotate_failed"
                end
            end
        end
    end
    if not copy_file(
        pending_path("overrides"), snapshot_file(1, "overrides"))
        or not copy_file(
            pending_path("order"), snapshot_file(1, "order"))
        or not copy_file(
            pending_path("self_words"),
            snapshot_file(1, "self_words"))
        or not copy_file(
            pending_path("self_word_ops"),
            snapshot_file(1, "self_word_ops")) then
        return nil, "backup_rotate_failed"
    end

    local history = read_undo_lines()
    table.insert(history, 1, description)
    while #history > M.undo_limit do
        table.remove(history)
    end
    if not atomic_lines(history_path(), history) then
        return nil, "backup_history_failed"
    end
    if profile then
        profile:mark("undo_history")
    end
    remove_pending()
    M.pending_memory = nil
    append_history(action, input, word, details or "-")
    if profile then
        profile:mark("operation_history")
    end
    return true
end

function M.rollback_pending()
    if M.pending_memory then
        local override_ok = restore_capture(
            M.pending_memory.overrides, M.override_file)
        local order_ok = restore_capture(
            M.pending_memory.order, M.order_file)
        local self_word_ok = restore_capture(
            M.pending_memory.self_words, M.self_word_file)
        local self_word_ops_ok = restore_capture(
            M.pending_memory.self_word_ops, M.self_word_ops_file)
        M.pending_memory = nil
        remove_pending()
        M.overrides = nil
        M.override_lookup = nil
        clear_self_word_cache()
        M.signature_cache = nil
        M.invalidate_effective_index()
        return override_ok and order_ok and self_word_ok and self_word_ops_ok
    end
    local meta_file = meta_path()
    local meta = meta_file and io.open(data_path(meta_file), "r")
    if not meta then
        return true
    end
    meta:close()
    local override_ok = restore_file(
        pending_path("overrides"), M.override_file)
    local order_ok = restore_file(
        pending_path("order"), M.order_file)
    local self_word_ok = restore_file(
        pending_path("self_words"), M.self_word_file)
    local self_word_ops_ok = restore_file(
        pending_path("self_word_ops"), M.self_word_ops_file)
    local ok = override_ok and order_ok and self_word_ok and self_word_ops_ok
    remove_pending()
    M.overrides = nil
    M.override_lookup = nil
    clear_self_word_cache()
    M.signature_cache = nil
    M.invalidate_effective_index()
    return ok
end

function M.commit(entries, action, input, word, defer_finish, profile)
    load_overrides()
    local changed = 0
    local affected_codes = {}
    local now = os.time()
    local device = installation_id()
    for _, entry in ipairs(entries or {}) do
        if entry.active ~= entry.initial_active
            or entry.code ~= entry.original_code then
            changed = changed + 1
            table.insert(affected_codes, entry.base_code)
            table.insert(affected_codes, entry.original_code)
            table.insert(affected_codes, entry.code)
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
        M.rollback_pending()
        return nil, "no_change"
    end
    if not write_overrides() then
        M.rollback_pending()
        return nil, "override_write_failed"
    end
    M.invalidate_effective_codes(affected_codes)
    if profile then
        profile:mark("overrides_write")
    end
    local self_updates = {}
    for _, entry in ipairs(entries or {}) do
        if entry.path == M.self_word_dict_file
            and (entry.active ~= entry.initial_active
                or entry.code ~= entry.original_code) then
            if entry.code ~= entry.original_code then
                table.insert(self_updates, {
                    word = entry.word,
                    code = entry.original_code,
                    active = false,
                })
            end
            table.insert(self_updates, {
                word = entry.word,
                code = entry.active and entry.code or entry.original_code,
                active = entry.active,
            })
        end
    end
    if #self_updates > 0 then
        local self_ok, self_err = M.update_self_words(self_updates)
        if not self_ok then
            M.rollback_pending()
            return nil, self_err
        end
    end
    if profile then
        profile:mark("self_words_write")
    end
    if not defer_finish then
        local finished, finish_err =
            M.finish(action, input, word, tostring(changed), profile)
        if not finished then
            M.rollback_pending()
            return nil, finish_err
        end
    end
    return true
end

function M.record_order(action, input, word, profile)
    return M.finish(action, input, word, "same_code", profile)
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
    table.insert(parts,
        M.self_word_file .. ":" .. file_fingerprint(M.self_word_file))
    table.insert(parts,
        M.self_word_ops_file .. ":" .. file_fingerprint(M.self_word_ops_file))
    M.signature_cache = table.concat(parts, "|")
    return M.signature_cache
end

function M.undo_items()
    local labels = {
        promote = "前移",
        demote = "后移",
        delete = "删除",
        make_word = "造词",
    }
    local result = {}
    for index, line in ipairs(read_undo_lines()) do
        local timestamp, action, input, word =
            string.match(line, "^([^\t]+)\t([^\t]+)\t([^\t]+)\t([^\t]+)")
        table.insert(result, {
            index = index,
            timestamp = tonumber(timestamp) or 0,
            action = action,
            input = input,
            word = word,
            label = table.concat({
                labels[action] or action or "操作",
                word or "",
                input or "",
            }, " "),
        })
    end
    return result
end

function M.undo(index)
    index = tonumber(index) or 1
    local history = read_undo_lines()
    if index < 1 or index > #history then
        return nil, "nothing_to_undo"
    end
    local description = history[index]
    if not restore_file(snapshot_file(index, "overrides"), M.override_file)
        or not restore_file(snapshot_file(index, "order"), M.order_file)
        or not restore_file(snapshot_file(index, "self_words"), M.self_word_file)
        or not restore_file(
            snapshot_file(index, "self_word_ops"),
            M.self_word_ops_file) then
        return nil, "undo_restore_failed"
    end

    local survivors = {}
    for old_slot = index + 1, #history do
        local new_slot = old_slot - index
        survivors[new_slot] = {}
        for _, kind in ipairs(M.undo_kinds) do
            local temp = undo_path(
                "shift_" .. tostring(new_slot)
                    .. "." .. kind .. ".tsv")
            if not copy_file(snapshot_file(old_slot, kind), temp) then
                return nil, "undo_history_shift_failed"
            end
            survivors[new_slot][kind] = temp
        end
    end
    for slot = 1, M.undo_limit do
        for _, kind in ipairs(M.undo_kinds) do
            os.remove(data_path(snapshot_file(slot, kind)))
        end
    end
    local remaining = {}
    for old_slot = index + 1, #history do
        table.insert(remaining, history[old_slot])
    end
    for slot, files in pairs(survivors) do
        for kind, temp in pairs(files) do
            if not copy_file(temp, snapshot_file(slot, kind)) then
                return nil, "undo_history_shift_failed"
            end
            os.remove(data_path(temp))
        end
    end
    if not atomic_lines(history_path(), remaining) then
        return nil, "undo_history_write_failed"
    end
    remove_pending()
    M.overrides = nil
    M.override_lookup = nil
    clear_self_word_cache()
    M.signature_cache = nil
    M.invalidate_effective_index()
    append_history("undo", "-", "-", description)
    return true, description
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

local function bootstrap_undo_storage()
    if not ensure_undo_directory() then
        return
    end
    local undo_history = history_path()
    if undo_history then
        ensure_file(undo_history, {})
    end
end

bootstrap_undo_storage()

return M
