local store = require("pantsu_store")
local M = {}

M.word_file = "pantsu.user.dict.yaml"
M.char_dict_file = "pantsu.danzi.dict.yaml"
M.build_state_file = "user.yaml"
M.optimization_state_file = "build/pantsu_make_word_optimized.state"
M.dictionary_files = {
    "pantsu.core.dict.yaml",
    "pantsu.danzi.dict.yaml",
    "pantsu.cizu.dict.yaml",
    "pantsu.temp.dict.yaml",
    "pantsu.user.dict.yaml",
    "pantsu.waigua.dict.yaml",
}
M.word_region_start = "#region <自造词>#"
M.word_region_end = "#endregion <自造词>#"

M.mode = false
M.buffer = ""
M.buffer_items = {}
M.char_codes = nil
M.char_code_list = nil
M.words_by_code = nil
M.loaded_words = false

local function utf8_chars(text)
    local chars = {}
    local start = 1
    while start <= #text do
        local next_start = utf8.offset(text, 2, start)
        if next_start then
            table.insert(chars, string.sub(text, start, next_start - 1))
            start = next_start
        else
            table.insert(chars, string.sub(text, start))
            break
        end
    end
    return chars
end

local function utf8_len(text)
    return utf8.len(text or "") or 0
end

local function utf8_drop_last(text)
    local len = utf8_len(text)
    if len <= 1 then
        return ""
    end
    local stop = utf8.offset(text, len) - 1
    return string.sub(text, 1, stop)
end

local function read_code_fields(line)
    local text, code = string.match(line, "^([^\t]+)\t([^\t%s]+)")
    return text, code
end

local function data_path(path)
    if string.sub(path, 1, 1) == "/" then
        return path
    end
    if rime_api and rime_api.get_user_data_dir then
        return rime_api.get_user_data_dir() .. "/" .. path
    end
    return path
end

local function read_lines(path)
    local lines = {}
    local file = io.open(data_path(path), "r")
    if not file then
        return lines
    end
    for line in file:lines() do
        table.insert(lines, line)
    end
    file:close()
    return lines
end

local function write_lines(path, lines)
    local target = data_path(path)
    local temp = target .. ".pantsu-make-word.tmp"
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

local function find_word_region(lines)
    local start_index, end_index
    for index, line in ipairs(lines) do
        if line == M.word_region_start then
            start_index = index
        elseif line == M.word_region_end and start_index then
            end_index = index
            break
        end
    end
    return start_index, end_index
end

local function read_last_build_time()
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

local function read_optimization_state()
    local file = io.open(data_path(M.optimization_state_file), "r")
    if not file then
        return nil
    end
    local value = file:read("*l")
    file:close()
    return value
end

local function write_optimization_state(value)
    local target = data_path(M.optimization_state_file)
    local temp = target .. ".tmp"
    local file = io.open(temp, "w")
    if not file then
        return false
    end
    file:write(value or "", "\n")
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

function M.load_char_codes()
    if M.char_codes then
        return
    end

    M.char_codes = {}
    M.char_code_list = {}
    local file = io.open(data_path(M.char_dict_file), "r")
    if not file then
        return
    end

    for line in file:lines() do
        if not string.match(line, "^%s*#") and not string.match(line, "^%s*$") then
            local text, code = read_code_fields(line)
            if text and code and utf8_len(text) == 1 and string.len(code) >= 3 then
                if not M.char_code_list[text] then
                    M.char_code_list[text] = {}
                end
                table.insert(M.char_code_list[text], code)
                local old = M.char_codes[text]
                if not old or string.len(code) > string.len(old) then
                    M.char_codes[text] = code
                end
            end
        end
    end

    file:close()
end

local function push_word(code, word)
    if not M.words_by_code[code] then
        M.words_by_code[code] = {}
    end

    local old = M.words_by_code[code]
    local fresh = { word }
    for _, item in ipairs(old) do
        if item ~= word then
            table.insert(fresh, item)
        end
    end
    M.words_by_code[code] = fresh
end

function M.load_words()
    if M.loaded_words then
        return
    end

    M.words_by_code = {}
    local lines = read_lines(M.word_file)
    local start_index, end_index = find_word_region(lines)
    if start_index and end_index then
        for index = start_index + 1, end_index - 1 do
            local line = lines[index]
            if not string.match(line, "^%s*#") and not string.match(line, "^%s*$") then
                local word, code = read_code_fields(line)
                if word and code then
                    push_word(code, word)
                end
            end
        end
    end
    M.loaded_words = true
end

function M.lookup(code)
    M.load_words()
    return M.words_by_code[code] or {}
end

local function code_startswith(code, prefix)
    return prefix and prefix ~= "" and string.sub(code, 1, string.len(prefix)) == prefix
end

function M.optimize_self_word_codes()
    local lines = read_lines(M.word_file)
    local start_index, end_index = find_word_region(lines)
    if not start_index or not end_index then
        return 0
    end

    local build_time = read_last_build_time()
    if build_time and read_optimization_state() == build_time then
        return 0
    end

    local entries = {}
    local targets_by_prefix = {}
    for index = start_index + 1, end_index - 1 do
        local word, code = read_code_fields(lines[index])
        local code_length = code and string.len(code) or 0
        if word and code_length > 1 and code_length <= 6 then
            local entry = {
                index = index,
                word = word,
                code = code,
                occupied = {},
            }
            table.insert(entries, entry)
            local prefix = string.sub(code, 1, code_length - 1)
            if not targets_by_prefix[prefix] then
                targets_by_prefix[prefix] = {}
            end
            table.insert(targets_by_prefix[prefix], entry)
        end
    end

    local function mark_occupied(word, code, self_region)
        local max_length = math.min(string.len(code), 5)
        for length = 1, max_length do
            local targets = targets_by_prefix[string.sub(code, 1, length)]
            if targets then
                for _, target in ipairs(targets) do
                    if not self_region or word ~= target.word then
                        target.occupied[length] = true
                    end
                end
            end
        end
    end

    for _, path in ipairs(M.dictionary_files) do
        if path == M.word_file then
            for index, line in ipairs(lines) do
                local word, code = read_code_fields(line)
                if word and code then
                    local self_region = index > start_index and index < end_index
                    mark_occupied(word, code, self_region)
                end
            end
        else
            local file = io.open(data_path(path), "r")
            if file then
                for line in file:lines() do
                    local word, code = read_code_fields(line)
                    if word and code then
                        mark_occupied(word, code, false)
                    end
                end
                file:close()
            end
        end
    end

    local changed = 0
    for _, entry in ipairs(entries) do
        local optimized = entry.code
        local shorter_length = string.len(entry.code) - 1
        if not entry.occupied[shorter_length] then
            optimized = string.sub(entry.code, 1, shorter_length)
        end
        if optimized ~= entry.code then
            lines[entry.index] = entry.word .. "\t" .. optimized
            changed = changed + 1
        end
    end

    if changed > 0 and not write_lines(M.word_file, lines) then
        return 0, "write_failed"
    end
    if build_time then
        write_optimization_state(build_time)
    end
    if changed > 0 then
        M.loaded_words = false
        M.words_by_code = nil
    end
    return changed
end

local function shortest_empty_prefix(full_code, target_word)
    local full_length = string.len(full_code)
    if full_length <= 1 then
        return full_code
    end

    local prefixes = {}
    for length = 1, full_length - 1 do
        prefixes[length] = string.sub(full_code, 1, length)
    end

    local occupied = {}
    local unresolved = full_length - 1
    for _, path in ipairs(M.dictionary_files) do
        local file = io.open(data_path(path), "r")
        if file then
            for line in file:lines() do
                local word, code = read_code_fields(line)
                local is_old_self_entry = path == M.word_file and word == target_word
                if word and code and not is_old_self_entry then
                    for length = 1, full_length - 1 do
                        if not occupied[length]
                            and code_startswith(code, prefixes[length]) then
                            occupied[length] = true
                            unresolved = unresolved - 1
                        end
                    end
                    if unresolved == 0 then
                        break
                    end
                end
            end
            file:close()
        end
        if unresolved == 0 then
            break
        end
    end

    for length = 1, full_length - 1 do
        if not occupied[length] then
            return string.sub(full_code, 1, length)
        end
    end
    return full_code
end

local function code_for_char(ch, typed_code)
    M.load_char_codes()
    local list = M.char_code_list[ch] or {}
    local best = nil

    if typed_code and typed_code ~= "" then
        for _, code in ipairs(list) do
            if code_startswith(code, typed_code) then
                if not best or string.len(code) > string.len(best) then
                    best = code
                end
            end
        end
    end

    return best or M.char_codes[ch]
end

local function selected_codes_for_word(word, typed_code)
    local chars = utf8_chars(word)
    local constraints = {}

    local function constrain(index, prefix, third)
        if index and chars[index] then
            constraints[index] = {
                prefix = prefix ~= "" and prefix or nil,
                third = third ~= "" and third or nil,
            }
        end
    end

    local length = string.len(typed_code or "")
    if #chars == 2 then
        constrain(1, string.sub(typed_code, 1, math.min(2, length)),
            length >= 5 and string.sub(typed_code, 5, 5) or nil)
        if length >= 3 then
            constrain(2, string.sub(typed_code, 3, math.min(4, length)),
                length >= 6 and string.sub(typed_code, 6, 6) or nil)
        end
    elseif #chars == 3 then
        for index = 1, math.min(3, length) do
            constrain(index, string.sub(typed_code, index, index),
                length >= index + 3
                    and string.sub(typed_code, index + 3, index + 3) or nil)
        end
    elseif #chars >= 4 then
        local indexes = { 1, 2, 3, #chars }
        for position = 1, math.min(4, length) do
            local index = indexes[position]
            local third = nil
            if position <= 2 and length >= position + 4 then
                third = string.sub(typed_code, position + 4, position + 4)
            end
            constrain(index, string.sub(typed_code, position, position), third)
        end
    end

    local selected = {}
    for index, ch in ipairs(chars) do
        local constraint = constraints[index]
        local best = nil
        for _, code in ipairs(M.char_code_list[ch] or {}) do
            local prefix_ok = not constraint or not constraint.prefix
                or code_startswith(code, constraint.prefix)
            local third_ok = not constraint or not constraint.third
                or string.sub(code, 3, 3) == constraint.third
            if prefix_ok and third_ok
                and (not best or string.len(code) > string.len(best)) then
                best = code
            end
        end
        selected[index] = best or code_for_char(
            ch, constraint and constraint.prefix or nil)
    end
    return selected
end

function M.code_for_word(word, items)
    M.load_char_codes()
    local chars = utf8_chars(word)
    if #chars < 2 then
        return nil, "too_short"
    end

    local codes = {}
    for index, ch in ipairs(chars) do
        local item = items and items[index]
        local code = code_for_char(ch, item and item.code)
        if not code or string.len(code) < 3 then
            return nil, "missing_code:" .. ch
        end
        table.insert(codes, code)
    end

    if #codes == 2 then
        return string.sub(codes[1], 1, 2)
            .. string.sub(codes[2], 1, 2)
            .. string.sub(codes[1], 3, 3)
            .. string.sub(codes[2], 3, 3)
    elseif #codes == 3 then
        return string.sub(codes[1], 1, 1)
            .. string.sub(codes[2], 1, 1)
            .. string.sub(codes[3], 1, 1)
            .. string.sub(codes[1], 3, 3)
            .. string.sub(codes[2], 3, 3)
            .. string.sub(codes[3], 3, 3)
    end

    return string.sub(codes[1], 1, 1)
        .. string.sub(codes[2], 1, 1)
        .. string.sub(codes[3], 1, 1)
        .. string.sub(codes[#codes], 1, 1)
        .. string.sub(codes[1], 3, 3)
        .. string.sub(codes[2], 3, 3)
end

local function unique_char_codes(ch)
    M.load_char_codes()
    local source = M.char_code_list[ch] or {}
    local result = {}
    local seen = {}
    for _, code in ipairs(source) do
        if string.len(code) >= 3 and not seen[code] then
            seen[code] = true
            table.insert(result, code)
        end
    end
    return result
end

function M.full_codes_for_word(word)
    local chars = utf8_chars(word)
    if #chars < 2 then
        return {}
    end

    local indexes
    if #chars <= 3 then
        indexes = {}
        for index = 1, #chars do
            table.insert(indexes, index)
        end
    else
        indexes = { 1, 2, 3, #chars }
    end

    local options = {}
    for _, index in ipairs(indexes) do
        local codes = unique_char_codes(chars[index])
        if #codes == 0 then
            return {}
        end
        options[index] = codes
    end

    local result = {}
    local seen = {}
    local selected = {}
    local function collect(position)
        if position <= #indexes then
            local index = indexes[position]
            for _, code in ipairs(options[index]) do
                selected[index] = code
                collect(position + 1)
            end
            return
        end

        local code
        if #chars == 2 then
            code = string.sub(selected[1], 1, 2)
                .. string.sub(selected[2], 1, 2)
                .. string.sub(selected[1], 3, 3)
                .. string.sub(selected[2], 3, 3)
        elseif #chars == 3 then
            code = string.sub(selected[1], 1, 1)
                .. string.sub(selected[2], 1, 1)
                .. string.sub(selected[3], 1, 1)
                .. string.sub(selected[1], 3, 3)
                .. string.sub(selected[2], 3, 3)
                .. string.sub(selected[3], 3, 3)
        else
            code = string.sub(selected[1], 1, 1)
                .. string.sub(selected[2], 1, 1)
                .. string.sub(selected[3], 1, 1)
                .. string.sub(selected[#chars], 1, 1)
                .. string.sub(selected[1], 3, 3)
                .. string.sub(selected[2], 3, 3)
        end
        if not seen[code] then
            seen[code] = true
            table.insert(result, code)
        end
    end
    collect(1)
    return result
end

function M.next_code_for_word(word, current_code)
    local next_codes = {}
    for _, full_code in ipairs(M.full_codes_for_word(word)) do
        if string.len(full_code) > string.len(current_code)
            and code_startswith(full_code, current_code) then
            next_codes[string.sub(full_code, 1, string.len(current_code) + 1)] = true
        end
    end

    local result
    for code in pairs(next_codes) do
        if result and result ~= code then
            return nil, "ambiguous_full_code"
        end
        result = code
    end
    if not result then
        return nil, "no_longer_code"
    end
    return result
end

function M.add_word(word, items)
    M.load_words()
    local code, err = M.code_for_word(word, items)
    if not code then
        return nil, err
    end
    code = shortest_empty_prefix(code, word)

    local lines = read_lines(M.word_file)
    local start_index, end_index = find_word_region(lines)
    if not start_index or not end_index then
        if #lines > 0 and lines[#lines] ~= "" then
            table.insert(lines, "")
        end
        table.insert(lines, M.word_region_start)
        table.insert(lines, M.word_region_end)
        start_index, end_index = find_word_region(lines)
    end

    local found = false
    local changed = false
    for index = end_index - 1, start_index + 1, -1 do
        local old_word, old_code = read_code_fields(lines[index])
        if old_word == word then
            if old_code == code and not found then
                found = true
            else
                table.remove(lines, index)
                end_index = end_index - 1
                changed = true
            end
        end
    end

    if not found then
        table.insert(lines, end_index, word .. "\t" .. code)
        changed = true
    end
    if changed and not write_lines(M.word_file, lines) then
        return nil, "write_failed"
    end

    if changed then
        store.invalidate_index()
        M.loaded_words = false
        M.words_by_code = nil
        M.load_words()
        store.record_order("make_word", code, word)
    else
        push_word(code, word)
    end
    return code
end

function M.start()
    M.mode = true
    M.buffer = ""
    M.buffer_items = {}
end

function M.cancel()
    M.mode = false
    M.buffer = ""
    M.buffer_items = {}
end

function M.append(text, code)
    if M.mode and text and text ~= "" then
        local chars = utf8_chars(text)
        local selected = nil
        if #chars > 1 and code and code ~= "" then
            selected = selected_codes_for_word(text, code)
        end
        for index, ch in ipairs(chars) do
            M.buffer = M.buffer .. ch
            table.insert(M.buffer_items, {
                text = ch,
                code = selected and selected[index] or code,
            })
        end
    end
end

function M.backspace_buffer()
    M.buffer = utf8_drop_last(M.buffer)
    table.remove(M.buffer_items)
end

function M.confirm()
    local word = M.buffer
    local items = M.buffer_items
    local code, err = M.add_word(word, items)
    if code then
        M.cancel()
    end
    return code, word, err
end

return M
