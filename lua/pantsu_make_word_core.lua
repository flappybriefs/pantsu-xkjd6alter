local store = require("pantsu_store")
local dynamic = require("pantsu_dynamic")
local profiler = require("pantsu_profiler")
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
M.last_error = nil
M.target_code = nil
M.last_codes = {}
M.last_refresh_codes = {}
M.pending_plan = nil
M.preview_text = nil

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
    local content = #lines > 0 and table.concat(lines, "\n") .. "\n" or ""
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
    local content = (value or "") .. "\n"
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

function M.restore_self_words()
    local lines = read_lines(M.word_file)
    local start_index, end_index = find_word_region(lines)
    local region_created = false
    if not start_index or not end_index then
        if #lines > 0 and lines[#lines] ~= "" then
            table.insert(lines, "")
        end
        table.insert(lines, M.word_region_start)
        table.insert(lines, M.word_region_end)
        start_index, end_index = find_word_region(lines)
        region_created = true
    end

    local seed = {}
    for index = start_index + 1, end_index - 1 do
        local word, code = read_code_fields(lines[index])
        if word and code then
            local active, effective_code =
                store.effective_entry(M.word_file, word, code)
            table.insert(seed, {
                word = word,
                code = effective_code ~= "" and effective_code or code,
                active = active,
            })
        end
    end
    local journal_authoritative = store.has_self_word_records()
    if not journal_authoritative then
        local seeded, seed_err = store.update_self_words(seed, true)
        if not seeded then
            return nil, seed_err
        end
    end

    local records = store.self_words()
    local found = {}
    local changed = region_created and 1 or 0
    for index = end_index - 1, start_index + 1, -1 do
        local word, code = read_code_fields(lines[index])
        local key = word and code and word .. "\t" .. code or nil
        local record = key and records[key] or nil
        if journal_authoritative and not record then
            table.remove(lines, index)
            end_index = end_index - 1
            changed = changed + 1
        elseif record then
            if not record.active or found[key] then
                table.remove(lines, index)
                end_index = end_index - 1
                changed = changed + 1
            else
                found[key] = true
            end
        end
    end
    local missing = {}
    for key, record in pairs(records) do
        if record.active and not found[key] then
            table.insert(missing, record)
        end
    end
    table.sort(missing, function(left, right)
        return left.word < right.word
    end)
    for _, record in ipairs(missing) do
        table.insert(lines, end_index,
            record.word .. "\t" .. record.code)
        end_index = end_index + 1
        changed = changed + 1
    end

    if changed > 0 and not write_lines(M.word_file, lines) then
        return nil, "write_failed"
    end
    local override_changed = false
    local cleared_words = {}
    for _, record in pairs(records) do
        local word = record.word
        local ok, cleared = true, false
        if not cleared_words[word] then
            ok, cleared = store.clear_word_overrides(M.word_file, word)
            cleared_words[word] = true
        end
        if not ok then
            return nil, cleared
        end
        override_changed = override_changed or cleared
    end
    if changed > 0 or override_changed then
        store.invalidate_index(M.word_file)
        M.loaded_words = false
        M.words_by_code = nil
    end
    return changed
end

function M.lookup(code)
    M.load_words()
    return M.words_by_code[code] or {}
end

local function code_startswith(code, prefix)
    return prefix and prefix ~= "" and string.sub(code, 1, string.len(prefix)) == prefix
end

local function word_min_code_length(word)
    local length = utf8_len(word)
    if length == 3 then
        return 3
    elseif length >= 2 then
        return 4
    end
    return 1
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
        store.invalidate_index(M.word_file)
        M.loaded_words = false
        M.words_by_code = nil
    end
    return changed
end

local function shortest_empty_prefix(full_code, target_word)
    local full_length = string.len(full_code)
    local minimum = word_min_code_length(target_word)
    if full_length <= minimum then
        return full_code
    end

    local prefixes = {}
    for length = minimum, full_length - 1 do
        prefixes[length] = string.sub(full_code, 1, length)
    end

    local occupied = {}
    local first = string.sub(full_code, 1, 1)
    for _, entry in ipairs(store.entries(first)) do
        if entry.active and entry.word ~= target_word then
            for length = minimum, full_length - 1 do
                if not occupied[length]
                    and code_startswith(entry.code, prefixes[length]) then
                    occupied[length] = true
                end
            end
        end
    end

    for length = minimum, full_length - 1 do
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

local function encode_word_codes(chars, codes)
    if #chars == 2 then
        return string.sub(codes[1], 1, 2)
            .. string.sub(codes[2], 1, 2)
            .. string.sub(codes[1], 3, 3)
            .. string.sub(codes[2], 3, 3)
    elseif #chars == 3 then
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
        .. string.sub(codes[#chars], 1, 1)
        .. string.sub(codes[1], 3, 3)
        .. string.sub(codes[2], 3, 3)
end

local function selected_full_codes(word, items)
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
    return chars, codes
end

function M.code_for_word(word, items)
    local chars, codes = selected_full_codes(word, items)
    if not chars then
        return nil, codes
    end
    return encode_word_codes(chars, codes)
end

local function fly_codes_for_char(ch, selected)
    local result = {}
    local seen = {}
    local suffix = string.sub(selected, 3)
    for _, code in ipairs(M.char_code_list[ch] or {}) do
        if string.len(code) >= 3 and string.sub(code, 3) == suffix
            and not seen[code] then
            seen[code] = true
            table.insert(result, code)
        end
    end
    if #result == 0 then
        table.insert(result, selected)
    end
    return result
end

function M.fly_codes_for_word(word, items)
    local chars, selected = selected_full_codes(word, items)
    if not chars then
        return nil, selected
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
        options[index] = fly_codes_for_char(chars[index], selected[index])
    end
    local result = {}
    local seen = {}
    local chosen = {}
    local function collect(position)
        if position <= #indexes then
            local index = indexes[position]
            for _, code in ipairs(options[index]) do
                chosen[index] = code
                collect(position + 1)
            end
            return
        end
        for index = 1, #chars do
            chosen[index] = chosen[index] or selected[index]
        end
        local code = encode_word_codes(chars, chosen)
        if not seen[code] then
            seen[code] = true
            table.insert(result, code)
        end
    end
    collect(1)
    table.sort(result)
    return result
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

        local code = encode_word_codes(chars, selected)
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

local function load_chain(input)
    local model = { entries = {}, by_code = {} }
    for _, entry in ipairs(store.entries(input)) do
        table.insert(model.entries, entry)
        if entry.active then
            if not model.by_code[entry.code] then
                model.by_code[entry.code] = {}
            end
            table.insert(model.by_code[entry.code], entry)
        end
    end
    return model
end

local function remove_from_code(model, entry)
    local list = model.by_code[entry.code] or {}
    for index = #list, 1, -1 do
        if list[index] == entry then
            table.remove(list, index)
            break
        end
    end
end

local function attach_to_code(model, entry, code)
    entry.code = code
    entry.active = true
    if not model.by_code[code] then
        model.by_code[code] = {}
    end
    table.insert(model.by_code[code], entry)
end

local function occupants(model, code, excluded_word)
    local result = {}
    for _, entry in ipairs(model.by_code[code] or {}) do
        if entry.active and entry.word ~= excluded_word then
            table.insert(result, entry)
        end
    end
    return result
end

local function extension_codes(word, current_code)
    local found = {}
    for _, full_code in ipairs(M.full_codes_for_word(word)) do
        if string.len(full_code) > string.len(current_code)
            and code_startswith(full_code, current_code) then
            local max_extra = math.min(2,
                string.len(full_code) - string.len(current_code))
            for extra = 1, max_extra do
                found[string.sub(
                    full_code, 1, string.len(current_code) + extra)] = true
            end
        end
    end
    local result = {}
    for code in pairs(found) do
        table.insert(result, code)
    end
    table.sort(result, function(left, right)
        if string.len(left) == string.len(right) then
            return left < right
        end
        return string.len(left) < string.len(right)
    end)
    return result
end

local function push_down(model, entry, visiting)
    if visiting[entry] then
        return nil, "code_cycle"
    end
    visiting[entry] = true
    local choices = extension_codes(entry.word, entry.code)
    if #choices == 0 then
        visiting[entry] = nil
        return nil, "occupied_code_cannot_move:" .. entry.word
    end
    for _, next_code in ipairs(choices) do
        local blocked = occupants(model, next_code, entry.word)
        local movable = true
        for _, occupant in ipairs(blocked) do
            local ok = push_down(model, occupant, visiting)
            if not ok then
                movable = false
                break
            end
        end
        if movable then
            remove_from_code(model, entry)
            attach_to_code(model, entry, next_code)
            visiting[entry] = nil
            return true
        end
    end
    local fallback = choices[1]
    if fallback then
        remove_from_code(model, entry)
        attach_to_code(model, entry, fallback)
        visiting[entry] = nil
        return true
    end
    visiting[entry] = nil
    return nil, "occupied_code_cannot_move:" .. entry.word
end

local function make_target_available(code, word)
    local model = load_chain(string.sub(code, 1, 1))
    local blocked = occupants(model, code, word)
    if #blocked > 0 and string.len(code) >= 6 then
        local words = { word }
        local seen = { [word] = true }
        for _, old_word in ipairs(dynamic.get_same_code_order(code)) do
            if not seen[old_word] then
                seen[old_word] = true
                table.insert(words, old_word)
            end
        end
        for _, entry in ipairs(blocked) do
            if not seen[entry.word] then
                seen[entry.word] = true
                table.insert(words, entry.word)
            end
        end
        return true, {}, words
    end

    local changed = false
    for _, entry in ipairs(blocked) do
        local ok, err = push_down(model, entry, {})
        if not ok then
            return nil, err
        end
        changed = true
    end
    if not changed then
        return true, {}
    end
    return true, model.entries
end

local function plan_summary(plan)
    local parts = { "保存 " .. plan.primary }
    local moved = 0
    for _, entry in ipairs(plan.moved_entries or {}) do
        if entry.active ~= entry.initial_active
            or entry.code ~= entry.original_code then
            moved = moved + 1
            if moved <= 2 then
                table.insert(parts, entry.word .. " "
                    .. entry.original_code .. "→"
                    .. (entry.active and entry.code or "删除"))
            end
        end
    end
    if moved > 2 then
        table.insert(parts, "另影响" .. tostring(moved - 2) .. "词")
    end
    if #plan.codes > 1 then
        table.insert(parts, "含" .. tostring(#plan.codes - 1) .. "个飞键码")
    end
    if plan.same_code_words then
        table.insert(parts, "六码同码置顶")
    end
    return "〔" .. table.concat(parts, "；") .. "〕"
end

function M.plan_word(word, items, target_code, profile)
    M.load_words()
    if profile then profile:mark("word_index_load") end
    local full_codes, err = M.fly_codes_for_word(word, items)
    if profile then profile:mark("fly_codes") end
    if not full_codes then
        return nil, err
    end
    local selected_full = M.code_for_word(word, items)
    if selected_full then
        local ordered = { selected_full }
        for _, full_code in ipairs(full_codes) do
            if full_code ~= selected_full then
                table.insert(ordered, full_code)
            end
        end
        full_codes = ordered
    end
    local matching_full
    if target_code and target_code ~= "" then
        if string.len(target_code) < word_min_code_length(word) then
            return nil, "target_code_too_short"
        end
        for _, full_code in ipairs(full_codes) do
            if code_startswith(full_code, target_code) then
                matching_full = full_code
                break
            end
        end
        if not matching_full then
            return nil, "target_code_mismatch:" .. table.concat(full_codes, "/")
        end
    end
    if profile then profile:mark("target_validate") end

    local codes = {}
    local seen_codes = {}
    local primary
    for _, full_code in ipairs(full_codes) do
        local code
        if matching_full == full_code then
            code = target_code
        else
            code = shortest_empty_prefix(full_code, word)
        end
        if code and code ~= "" and not seen_codes[code] then
            seen_codes[code] = true
            table.insert(codes, code)
        end
        if matching_full == full_code then
            primary = code
        end
    end
    primary = primary or codes[1]
    if profile then profile:mark("shortest_codes") end

    local moved_entries = {}
    local same_code_words
    if target_code and target_code ~= "" then
        local available, moved_or_err, same_code_order =
            make_target_available(target_code, word)
        if not available then
            return nil, moved_or_err
        end
        moved_entries = moved_or_err
        same_code_words = same_code_order
    end
    if profile then profile:mark("target_reorder") end

    local previous_codes = {}
    for _, record in pairs(store.self_words()) do
        if record.word == word and record.active then
            table.insert(previous_codes, record.code)
        end
    end
    if profile then profile:mark("previous_codes") end

    local plan = {
        word = word,
        codes = codes,
        primary = primary,
        moved_entries = moved_entries,
        target_code = target_code,
        same_code_words = same_code_words,
        previous_codes = previous_codes,
    }
    plan.summary = plan_summary(plan)
    return plan
end

local function word_file_with(word, codes)
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

    for index = end_index - 1, start_index + 1, -1 do
        local old_word = read_code_fields(lines[index])
        if old_word == word then
            table.remove(lines, index)
            end_index = end_index - 1
        end
    end

    for _, code in ipairs(codes) do
        table.insert(lines, end_index, word .. "\t" .. code)
        end_index = end_index + 1
    end
    return lines
end

function M.apply_plan(plan, profile)
    local own_profile = not profile
    profile = profile or profiler.start(
        "make_word_save",
        plan and plan.primary or "-",
        plan and plan.word or "-")
    if not plan or not plan.word or not plan.primary then
        profile:finish("failed", "missing_plan")
        return nil, "missing_plan"
    end
    if not store.begin(
        "make_word", plan.primary, plan.word, profile) then
        profile:finish("failed", "backup_failed")
        return nil, "backup_failed"
    end

    local moved = false
    for _, entry in ipairs(plan.moved_entries or {}) do
        if entry.active ~= entry.initial_active
            or entry.code ~= entry.original_code then
            moved = true
            break
        end
    end
    if moved then
        local moved_ok, moved_err = store.commit(
            plan.moved_entries, "make_word",
            plan.primary, plan.word, true, profile)
        if not moved_ok then
            store.rollback_pending()
            profile:finish("failed", tostring(moved_err))
            return nil, moved_err
        end
    end
    profile:mark("occupied_chain")

    local override_ok, override_changed =
        store.clear_word_overrides(M.word_file, plan.word)
    if not override_ok then
        store.rollback_pending()
        profile:finish("failed", tostring(override_changed))
        return nil, override_changed
    end
    profile:mark("clear_old_overrides")
    local journal_ok, journal_changed =
        store.replace_self_word(plan.word, plan.codes)
    if not journal_ok then
        store.rollback_pending()
        profile:finish("failed", tostring(journal_changed))
        return nil, journal_changed
    end
    profile:mark("self_word_journal")
    if not write_lines(
        M.word_file, word_file_with(plan.word, plan.codes)) then
        store.rollback_pending()
        M.restore_self_words()
        profile:finish("failed", "write_failed")
        return nil, "write_failed"
    end
    profile:mark("user_yaml_write")
    if plan.same_code_words
        and not dynamic.set_same_code_order(
            plan.primary, plan.same_code_words) then
        store.rollback_pending()
        M.restore_self_words()
        dynamic.invalidate()
        profile:finish("failed", "same_code_order_write_failed")
        return nil, "same_code_order_write_failed"
    end
    profile:mark("same_code_order")
    local finished, finish_err = store.finish(
        "make_word", plan.primary, plan.word,
        tostring(#plan.codes) .. "_codes", profile)
    if not finished then
        store.rollback_pending()
        M.restore_self_words()
        dynamic.invalidate()
        profile:finish("failed", tostring(finish_err))
        return nil, finish_err
    end

    if moved or override_changed or journal_changed then
        store.invalidate_index(M.word_file)
        M.loaded_words = false
        M.words_by_code = nil
    else
        for _, code in ipairs(plan.codes) do
            push_word(code, plan.word)
        end
    end
    profile:mark("word_cache_invalidate")
    M.last_codes = plan.codes
    local refresh_seen = {}
    M.last_refresh_codes = {}
    for _, code in ipairs(plan.previous_codes or {}) do
        if not refresh_seen[code] then
            refresh_seen[code] = true
            table.insert(M.last_refresh_codes, code)
        end
    end
    for _, code in ipairs(plan.codes) do
        if not refresh_seen[code] then
            refresh_seen[code] = true
            table.insert(M.last_refresh_codes, code)
        end
    end
    if own_profile then
        profile:finish("ok")
    end
    return plan.primary, nil, plan.moved_entries
end

function M.add_word(word, items, target_code)
    local plan, err = M.plan_word(word, items, target_code)
    if not plan then
        return nil, err
    end
    return M.apply_plan(plan)
end

function M.start(target_code)
    store.ensure_runtime_files()
    M.restore_self_words()
    M.mode = "manual"
    M.buffer = ""
    M.buffer_items = {}
    M.last_error = nil
    M.target_code = target_code
    M.last_codes = {}
    M.last_refresh_codes = {}
    M.pending_plan = nil
    M.preview_text = nil
end

function M.cancel()
    M.mode = false
    M.buffer = ""
    M.buffer_items = {}
    M.last_error = nil
    M.target_code = nil
    M.pending_plan = nil
    M.preview_text = nil
end

function M.append(text, code)
    if M.mode and text and text ~= "" then
        M.last_error = nil
        M.pending_plan = nil
        M.preview_text = nil
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
    M.last_error = nil
    M.pending_plan = nil
    M.preview_text = nil
    M.buffer = utf8_drop_last(M.buffer)
    table.remove(M.buffer_items)
end

function M.prepare_preview()
    if M.pending_plan or utf8_len(M.buffer) < 2 then
        return M.pending_plan
    end
    return M.preview()
end

function M.preview(profile)
    local own_profile = not profile
    profile = profile or profiler.start(
        "make_word_preview", M.target_code or "-", M.buffer)
    local plan, err = M.plan_word(
        M.buffer, M.buffer_items, M.target_code, profile)
    if not plan then
        M.last_error = err
        M.pending_plan = nil
        M.preview_text = nil
        profile:finish("failed", tostring(err))
        return nil, err
    end
    M.pending_plan = plan
    M.preview_text = plan.summary
    M.last_error = nil
    if own_profile then
        profile:finish("ok")
    end
    return plan
end

function M.confirm(profile)
    local word = M.buffer
    if not M.pending_plan then
        local plan, preview_err = M.preview(profile)
        if not plan then
            return nil, word, preview_err
        end
    end
    local code, err, moved_entries =
        M.apply_plan(M.pending_plan, profile)
    if code then
        M.cancel()
    else
        M.last_error = err
    end
    return code, word, err, moved_entries
end

return M
