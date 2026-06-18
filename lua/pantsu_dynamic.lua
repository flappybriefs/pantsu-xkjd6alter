local M = {}

M.state_file = "build/pantsu_dynamic_candidates.tsv"
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
    for line in file:lines() do
        local kind, root, first, second =
            string.match(line, "^([^\t]+)\t([^\t]*)\t?([^\t]*)\t?(.*)$")
        if kind == "build" then
            state_build = root
        elseif kind == "root" and root ~= "" then
            M.roots[root] = { entries = {}, suppress = {} }
        elseif kind == "suppress" and M.roots[root] and first ~= "" then
            M.roots[root].suppress[first] = true
        elseif kind == "entry" and M.roots[root]
            and first ~= "" and second ~= "" then
            local word, code = string.match(second, "^([^\t]+)\t([^\t]+)$")
            if word and code then
                table.insert(M.roots[root].entries, { word = word, code = code })
                M.roots[root].suppress[word] = true
            end
        end
    end
    file:close()

    if state_build ~= M.build_time then
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
    file:write("build\t", M.build_time or "", "\n")

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
        for index, entry in ipairs(state.entries) do
            file:write("entry\t", root, "\t", tostring(index), "\t",
                entry.word, "\t", entry.code, "\n")
        end
    end
    file:close()
    if not os.rename(temp, target) then
        os.remove(temp)
        return false
    end
    return true
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

local function snapshot_root(root, extra_suppress)
    for _, word in ipairs(extra_suppress or {}) do
        for _, old_state in pairs(M.roots) do
            local kept = {}
            for _, entry in ipairs(old_state.entries) do
                if entry.word ~= word then
                    table.insert(kept, entry)
                end
            end
            old_state.entries = kept
            old_state.suppress[word] = true
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

    local state = { entries = {}, suppress = {} }
    local order = 0
    for _, path in ipairs(M.dictionary_files) do
        local file = io.open(data_path(path), "r")
        if file then
            for line in file:lines() do
                local word, code = read_code_fields(line)
                if word and code
                    and string.sub(code, 1, string.len(root)) == root then
                    order = order + 1
                    table.insert(state.entries, {
                        word = word,
                        code = code,
                        order = order,
                    })
                    state.suppress[word] = true
                end
            end
            file:close()
        end
    end
    for _, word in ipairs(extra_suppress or {}) do
        state.suppress[word] = true
    end
    table.sort(state.entries, function(left, right)
        if left.code == right.code then
            return left.order < right.order
        end
        return left.code < right.code
    end)
    M.roots[root] = state
end

function M.refresh_codes(codes, suppressed_words, preferred_root)
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
    snapshot_root(root, suppressed_words)
    return write_state()
end

function M.refresh_entries(entries, preferred_root)
    local codes = {}
    local words = {}
    for _, entry in ipairs(entries or {}) do
        if not entry.active or entry.code ~= entry.original_code then
            table.insert(words, entry.word)
            table.insert(codes, entry.original_code)
            if entry.active then
                table.insert(codes, entry.code)
            end
        end
    end
    return M.refresh_codes(codes, words, preferred_root)
end

function M.match(input)
    ensure_current_build()
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
