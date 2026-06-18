local core = require("pantsu_make_word_core")

local kAccepted = 1
local kNoop = 2
local action_names = {
    ["8"] = "promote",
    ["9"] = "demote",
    ["0"] = "delete",
}

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

local function load_sources()
    local model = {
        files = {},
        entries = {},
        by_code = {},
        by_word = {},
    }
    for _, path in ipairs(core.dictionary_files) do
        local file = io.open(data_path(path), "r")
        if file then
            local source = { path = path, lines = {}, changed = false }
            for line in file:lines() do
                table.insert(source.lines, line)
                local word, code = read_code_fields(line)
                if word and code then
                    local entry = {
                        source = source,
                        index = #source.lines,
                        word = word,
                        code = code,
                        original_code = code,
                        active = true,
                    }
                    table.insert(model.entries, entry)
                    if not model.by_code[code] then
                        model.by_code[code] = {}
                    end
                    table.insert(model.by_code[code], entry)
                    if not model.by_word[word] then
                        model.by_word[word] = {}
                    end
                    table.insert(model.by_word[word], entry)
                end
            end
            file:close()
            table.insert(model.files, source)
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

local function detach(model, entry)
    remove_from_code(model, entry)
    entry.active = false
end

local function occupants(model, code, excluded)
    local result = {}
    for _, entry in ipairs(model.by_code[code] or {}) do
        if entry.active and entry ~= excluded then
            table.insert(result, entry)
        end
    end
    return result
end

local function locate_entry(model, word, input)
    local exact
    local best
    local ambiguous = false
    for _, entry in ipairs(model.by_word[word] or {}) do
        if entry.active and string.sub(entry.code, 1, string.len(input)) == input then
            if entry.code == input then
                if exact and exact ~= entry then
                    return nil, "ambiguous_exact_entry"
                end
                exact = entry
            elseif not best or string.len(entry.code) < string.len(best.code) then
                best = entry
                ambiguous = false
            elseif string.len(entry.code) == string.len(best.code) then
                ambiguous = true
            end
        end
    end
    if exact then
        return exact
    end
    if ambiguous then
        return nil, "ambiguous_completion_entry"
    end
    return best, best and nil or "entry_not_found"
end

local function push_down(model, entry, visiting)
    if visiting[entry] then
        return nil, "code_cycle"
    end
    visiting[entry] = true

    local next_code, err = core.next_code_for_word(entry.word, entry.code)
    if not next_code then
        visiting[entry] = nil
        return nil, err
    end

    local blocked = occupants(model, next_code, entry)
    if #blocked > 1 then
        visiting[entry] = nil
        return nil, "multiple_occupants:" .. next_code
    end
    if #blocked == 1 then
        local ok
        ok, err = push_down(model, blocked[1], visiting)
        if not ok then
            visiting[entry] = nil
            return nil, err
        end
    end

    remove_from_code(model, entry)
    attach_to_code(model, entry, next_code)
    visiting[entry] = nil
    return true
end

local function promote(model, entry)
    if string.len(entry.code) <= 1 then
        return nil, "code_too_short"
    end
    local old_code = entry.code
    local target_code = string.sub(old_code, 1, string.len(old_code) - 1)
    detach(model, entry)

    local blocked = occupants(model, target_code)
    if #blocked > 1 then
        return nil, "multiple_occupants:" .. target_code
    end
    if #blocked == 1 then
        local ok, err = push_down(model, blocked[1], {})
        if not ok then
            return nil, err
        end
    end
    attach_to_code(model, entry, target_code)
    return true
end

local function demote(model, entry)
    local target_code, err = core.next_code_for_word(entry.word, entry.code)
    if not target_code then
        return nil, err
    end
    detach(model, entry)

    local blocked = occupants(model, target_code)
    if #blocked > 1 then
        return nil, "multiple_occupants:" .. target_code
    end
    if #blocked == 1 then
        local ok
        ok, err = push_down(model, blocked[1], {})
        if not ok then
            return nil, err
        end
    end
    attach_to_code(model, entry, target_code)
    return true
end

local function following_candidate_words(context)
    local composition = context.composition
    if not composition or composition:empty() then
        return {}
    end
    local segment = composition:back()
    if not segment or not segment.menu then
        return {}
    end

    local start_index = segment.selected_index + 1
    segment.menu:prepare(start_index + 200)
    local count = segment.menu:candidate_count()
    local result = {}
    for index = start_index, math.min(count - 1, start_index + 199) do
        local candidate = segment:get_candidate_at(index)
        if candidate and candidate.text and candidate.text ~= "" then
            table.insert(result, candidate.text)
        end
    end
    return result
end

local function descendant_entry(model, word, prefix)
    local best
    local ambiguous = false
    for _, entry in ipairs(model.by_word[word] or {}) do
        if entry.active
            and string.len(entry.code) > string.len(prefix)
            and string.sub(entry.code, 1, string.len(prefix)) == prefix then
            if not best or string.len(entry.code) < string.len(best.code) then
                best = entry
                ambiguous = false
            elseif string.len(entry.code) == string.len(best.code) then
                ambiguous = true
            end
        end
    end
    if ambiguous then
        return nil
    end
    return best
end

local function pull_candidates(model, vacancy, candidate_words)
    for _, word in ipairs(candidate_words) do
        if #occupants(model, vacancy) > 0 then
            break
        end
        local next_entry = descendant_entry(model, word, vacancy)
        if next_entry then
            local old_code = next_entry.code
            remove_from_code(model, next_entry)
            attach_to_code(model, next_entry, vacancy)
            vacancy = old_code
        end
    end
end

local function demote_and_pull(model, entry, candidate_words)
    local vacancy = entry.code
    local ok, err = demote(model, entry)
    if not ok then
        return nil, err
    end
    pull_candidates(model, vacancy, candidate_words)
    return true
end

local function delete_and_pull(model, entry, candidate_words)
    local vacancy = entry.code
    detach(model, entry)
    pull_candidates(model, vacancy, candidate_words)
    return true
end

local function replace_code(line, code)
    local prefix, suffix = string.match(line, "^([^\t]+\t)[^\t%s]+(.*)$")
    if not prefix then
        return line
    end
    return prefix .. code .. suffix
end

local function prepare_changes(model)
    local changed_files = {}
    for _, entry in ipairs(model.entries) do
        if not entry.active then
            entry.source.lines[entry.index] = false
            entry.source.changed = true
        elseif entry.code ~= entry.original_code then
            entry.source.lines[entry.index] =
                replace_code(entry.source.lines[entry.index], entry.code)
            entry.source.changed = true
        end
    end
    for _, source in ipairs(model.files) do
        if source.changed then
            table.insert(changed_files, source)
        end
    end
    return changed_files
end

local function write_sources(sources)
    local prepared = {}
    for _, source in ipairs(sources) do
        local target = data_path(source.path)
        local temp = target .. ".pantsu-candidate-editor.tmp"
        local file = io.open(temp, "w")
        if not file then
            for _, item in ipairs(prepared) do
                os.remove(item.temp)
            end
            return nil, "open_failed:" .. source.path
        end
        for _, line in ipairs(source.lines) do
            if line ~= false then
                file:write(line, "\n")
            end
        end
        file:close()
        table.insert(prepared, { temp = temp, target = target, path = source.path })
    end

    for _, item in ipairs(prepared) do
        if not os.rename(item.temp, item.target) then
            for _, pending in ipairs(prepared) do
                os.remove(pending.temp)
            end
            return nil, "rename_failed:" .. item.path
        end
    end
    return true
end

local function write_log(action, entries)
    local file = io.open(data_path("build/pantsu_candidate_editor.log"), "a")
    if not file then
        return
    end
    local timestamp = os.date("%Y-%m-%d %H:%M:%S")
    for _, entry in ipairs(entries) do
        if not entry.active or entry.code ~= entry.original_code then
            file:write(timestamp, "\t", action, "\t", entry.source.path, "\t",
                entry.word, "\t", entry.original_code, "\t",
                entry.active and entry.code or "<deleted>", "\n")
        end
    end
    file:close()
end

local function adjust(action, context, word, input)
    local model = load_sources()
    local entry, err = locate_entry(model, word, input)
    if not entry then
        return nil, err
    end

    local ok
    if action == "promote" then
        ok, err = promote(model, entry)
    elseif action == "demote" then
        ok, err = demote_and_pull(
            model, entry, following_candidate_words(context))
    else
        ok, err = delete_and_pull(model, entry, following_candidate_words(context))
    end
    if not ok then
        return nil, err
    end

    local sources = prepare_changes(model)
    if #sources == 0 then
        return nil, "no_change"
    end
    ok, err = write_sources(sources)
    if not ok then
        return nil, err
    end
    write_log(action, model.entries)
    return true
end

local function processor(key_event, env)
    if key_event:release() or key_event:ctrl() or key_event:alt() or core.mode then
        return kNoop
    end

    local keycode = key_event.keycode
    if not keycode or keycode < 0x30 or keycode > 0x39 then
        return kNoop
    end
    local action = action_names[string.char(keycode)]
    if not action then
        return kNoop
    end

    local context = env.engine.context
    if not context:has_menu() or context.input == "" then
        return kNoop
    end
    local candidate = context:get_selected_candidate()
    if not candidate or not candidate.text or candidate.text == "" then
        return kNoop
    end

    local ok, err = adjust(action, context, candidate.text, context.input)
    if not ok then
        if log and log.warning then
            log.warning("candidate editor: " .. (err or "unknown error"))
        end
        return kAccepted
    end

    context:clear()
    return kAccepted
end

return { func = processor }
