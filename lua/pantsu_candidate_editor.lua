local core = require("pantsu_make_word_core")
local dynamic = require("pantsu_dynamic")
local store = require("pantsu_store")

local kAccepted = 1
local kNoop = 2
local action_names = {
    ["8"] = "promote",
    ["9"] = "demote",
    ["0"] = "delete",
}
local pending_delete = nil

local function is_macos()
    if rime_api and rime_api.get_distribution_code_name then
        local code = string.lower(
            rime_api.get_distribution_code_name() or "")
        return string.find(code, "squirrel", 1, true) ~= nil
    end
    return false
end

local function has_active_input(context)
    return context.input ~= "" or context:has_menu()
end

local function is_undo_shortcut(key_event)
    if key_event.keycode ~= 0x7a or key_event:shift()
        or key_event:alt() or key_event:super() then
        return false
    end
    return key_event:ctrl()
end

local function is_history_shortcut(key_event)
    if key_event.keycode ~= 0x68
        or key_event:alt() or key_event:super()
        or not key_event:ctrl() then
        return false
    end
    return is_macos() or key_event:shift()
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

local function code_startswith(code, prefix)
    return string.sub(code, 1, string.len(prefix)) == prefix
end

local function word_min_code_length(word)
    local length = utf8.len(word or "") or 0
    if length == 3 then
        return 3
    elseif length >= 2 then
        return 4
    end
    return 1
end

local function load_chain(input)
    local model = {
        entries = {},
        by_code = {},
        by_word = {},
    }
    for _, entry in ipairs(store.entries(input)) do
        table.insert(model.entries, entry)
        if entry.active then
            if not model.by_code[entry.code] then
                model.by_code[entry.code] = {}
            end
            table.insert(model.by_code[entry.code], entry)
            if not model.by_word[entry.word] then
                model.by_word[entry.word] = {}
            end
            table.insert(model.by_word[entry.word], entry)
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

local function locate_entry(model, word, input, candidate_id)
    if candidate_id and candidate_id ~= "" then
        for _, entry in ipairs(model.entries) do
            if entry.id == candidate_id and entry.active then
                return entry
            end
        end
    end
    local exact
    local best
    local ambiguous = false
    for _, entry in ipairs(model.by_word[word] or {}) do
        if entry.active and code_startswith(entry.code, input) then
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

local function extension_codes(word, current_code)
    local found = {}
    for _, full_code in ipairs(core.full_codes_for_word(word)) do
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

    local candidates = extension_codes(entry.word, entry.code)
    if #candidates == 0 then
        visiting[entry] = nil
        return nil, "no_longer_code:" .. entry.word
    end

    local groups = {}
    for _, code in ipairs(candidates) do
        local length = string.len(code)
        if not groups[length] then
            groups[length] = {}
        end
        table.insert(groups[length], code)
    end

    local last_error
    local lengths = {}
    for length in pairs(groups) do
        table.insert(lengths, length)
    end
    table.sort(lengths)
    for _, length in ipairs(lengths) do
        local choices = groups[length]
        if #choices == 1 then
            local next_code = choices[1]
            local blocked = occupants(model, next_code, entry)
            if #blocked == 0 then
                remove_from_code(model, entry)
                attach_to_code(model, entry, next_code)
                visiting[entry] = nil
                return true
            elseif #blocked == 1 then
                local ok = push_down(model, blocked[1], visiting)
                if ok then
                    remove_from_code(model, entry)
                    attach_to_code(model, entry, next_code)
                    visiting[entry] = nil
                    return true
                end
                remove_from_code(model, entry)
                attach_to_code(model, entry, next_code)
                visiting[entry] = nil
                return true
            else
                remove_from_code(model, entry)
                attach_to_code(model, entry, next_code)
                visiting[entry] = nil
                return true
            end
        else
            last_error = "ambiguous_full_code:" .. entry.word
        end
    end

    visiting[entry] = nil
    return nil, last_error or ("no_available_code:" .. entry.word)
end

local function promote(model, entry)
    if string.len(entry.code) <= word_min_code_length(entry.word) then
        return nil, "word_code_too_short"
    end
    local target_code = string.sub(entry.code, 1, string.len(entry.code) - 1)
    detach(model, entry)

    local blocked = occupants(model, target_code)
    if #blocked > 0 then
        local visiting = {}
        for _, occupant in ipairs(blocked) do
            local ok, err = push_down(model, occupant, visiting)
            if not ok then
                return nil, err
            end
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
    if #blocked == 1 then
        push_down(model, blocked[1], {})
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

local function same_code_candidate_words(context, model, code)
    local composition = context.composition
    if not composition or composition:empty() then
        return {}
    end
    local segment = composition:back()
    if not segment or not segment.menu then
        return {}
    end

    segment.menu:prepare(200)
    local count = segment.menu:candidate_count()
    local result = {}
    local seen = {}
    for index = 0, math.min(count - 1, 199) do
        local candidate = segment:get_candidate_at(index)
        local word = candidate and candidate.text
        if word and not seen[word] then
            for _, item in ipairs(model.by_word[word] or {}) do
                if item.active and item.code == code then
                    table.insert(result, word)
                    seen[word] = true
                    break
                end
            end
        end
    end
    return result
end

local function move_same_code(context, model, entry, direction)
    local words = same_code_candidate_words(context, model, entry.code)
    for index, word in ipairs(words) do
        local target = direction == "promote" and index - 1 or index + 1
        if word == entry.word and target >= 1 and target <= #words then
            if not store.begin(direction, entry.code, entry.word) then
                return false
            end
            words[index], words[target] = words[target], words[index]
            local ok = dynamic.set_same_code_order(entry.code, words)
            if ok then
                store.record_order(direction, entry.code, entry.word)
            end
            return ok
        end
    end
    return false
end

local function descendant_entry(model, word, prefix)
    local best
    local ambiguous = false
    for _, entry in ipairs(model.by_word[word] or {}) do
        if entry.active
            and string.len(entry.code) > string.len(prefix)
            and code_startswith(entry.code, prefix) then
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

local function promote_and_pull(model, entry, candidate_words)
    local vacancy = entry.code
    local ok, err = promote(model, entry)
    if not ok then
        return nil, err
    end
    pull_candidates(model, vacancy, candidate_words)
    return true
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

local function write_error(action, word, input, err)
    store.rotate_log("build/pantsu_candidate_editor.error.log", 262144)
    local file = io.open(data_path("build/pantsu_candidate_editor.error.log"), "a")
    if not file then
        return
    end
    file:write(os.date("%Y-%m-%d %H:%M:%S"), "\t",
        action, "\t", word, "\t", input, "\t",
        err or "unknown error", "\n")
    file:close()
end

local function write_log(action, entries)
    store.rotate_log("build/pantsu_candidate_editor.log", 524288)
    local file = io.open(data_path("build/pantsu_candidate_editor.log"), "a")
    if not file then
        return
    end
    local timestamp = os.date("%Y-%m-%d %H:%M:%S")
    for _, entry in ipairs(entries) do
        if not entry.active or entry.code ~= entry.original_code then
            file:write(timestamp, "\t", action, "\t", entry.path, "\t",
                entry.word, "\t", entry.original_code, "\t",
                entry.active and entry.code or "<deleted>", "\n")
        end
    end
    file:close()
end

local function adjust(action, context, word, input, candidate_id)
    local root = input
    local model = load_chain(root)
    local entry, err = locate_entry(model, word, input, candidate_id)
    if not entry then
        return nil, err
    end

    if action == "promote" and entry.code == input
        and string.len(input) > 1 then
        root = string.sub(input, 1, string.len(input) - 1)
        model = load_chain(root)
        entry, err = locate_entry(model, word, input, candidate_id)
        if not entry then
            return nil, err
        end
    end

    local ok
    local following = following_candidate_words(context)
    if action == "promote" then
        if move_same_code(context, model, entry, "promote") then
            return true, nil, input
        end
        ok, err = promote_and_pull(model, entry, following)
    elseif action == "demote" then
        ok, err = demote_and_pull(model, entry, following)
        if not ok and err == "no_longer_code"
            and move_same_code(context, model, entry, "demote") then
            write_log(action, model.entries)
            return true, nil, input
        end
    else
        ok, err = delete_and_pull(model, entry, following)
    end
    if not ok then
        return nil, err
    end

    if not store.begin(action, input, word) then
        return nil, "backup_failed"
    end
    ok, err = store.commit(model.entries, action, input, word)
    if not ok then
        return nil, err
    end
    local dynamic_root = root
    if entry.original_code == input and string.len(input) > 1 then
        dynamic_root = string.sub(input, 1, string.len(input) - 1)
    end
    if string.len(dynamic_root) > 4 then
        dynamic_root = string.sub(dynamic_root, 1, 4)
    end
    if not dynamic.refresh_entries(model.entries, dynamic_root) then
        write_error(action, word, input, "dynamic_refresh_failed")
    end
    write_log(action, model.entries)
    local focus_input = input
    if action == "promote"
        and string.len(entry.code) < string.len(input) then
        focus_input = entry.code
    end
    return true, nil, focus_input
end

local function refresh_after_adjust(
    context, action, word, old_index, focus_input)
    if focus_input and focus_input ~= "" and focus_input ~= context.input then
        context.input = focus_input
    end
    context:refresh_non_confirmed_composition()
    local composition = context.composition
    if not composition or composition:empty() then
        return
    end
    local segment = composition:back()
    if not segment or not segment.menu then
        return
    end

    segment.menu:prepare(200)
    local count = segment.menu:candidate_count()
    if count == 0 then
        return
    end

    if action ~= "delete" then
        for index = 0, math.min(count - 1, 199) do
            local candidate = segment:get_candidate_at(index)
            if candidate and candidate.text == word then
                segment.selected_index = index
                return
            end
        end
    end
    segment.selected_index = math.min(old_index, count - 1)
end

local function upper_level_hint(code, word)
    if not code or string.len(code) <= 1 then
        return nil
    end
    if string.len(code) <= word_min_code_length(word) then
        return "〔已到该词允许的最短码〕"
    end
    local parent = string.sub(code, 1, string.len(code) - 1)
    local occupant
    for _, entry in ipairs(store.entries(parent)) do
        if entry.active and entry.code == parent and entry.word ~= word then
            occupant = entry.word
            break
        end
    end
    if occupant then
        return "〔再前移：" .. parent .. " 当前为“" .. occupant .. "”〕"
    end
    return "〔再前移：" .. parent .. " 当前为空码〕"
end

local error_messages = {
    entry_not_found = "〔调频失败：词条已变化〕",
    ambiguous_exact_entry = "〔调频失败：存在重复词条〕",
    ambiguous_completion_entry = "〔调频失败：候选身份不明确〕",
    ambiguous_full_code = "〔调频失败：存在多个后续码〕",
    no_longer_code = "〔无法继续后移〕",
    no_change = "〔没有可应用的变化〕",
    word_code_too_short = "〔已到该词允许的最短码〕",
    backup_failed = "〔调频失败：无法创建撤销点〕",
    override_write_failed = "〔调频失败：覆盖层写入失败〕",
    self_word_write_failed = "〔调频失败：自造词记录写入失败〕",
}

local function show_error(context, err)
    local message = error_messages[err]
        or error_messages[string.match(err or "", "^[^:]+")]
        or "〔调频失败：" .. tostring(err or "未知错误") .. "〕"
    dynamic.set_status(context.input, message, "transient")
    context:refresh_non_confirmed_composition()
end

local function candidate_identity(candidate)
    return string.match(candidate.type or "", "^[^|]+|(.+)$")
end

local function clear_transient_status(context, refresh)
    if dynamic.status_kind() ~= "transient" then
        return
    end
    dynamic.clear_status()
    if refresh and has_active_input(context) then
        context:refresh_non_confirmed_composition()
    end
end

local function cancel_delete_confirmation(context, refresh)
    if not pending_delete then
        return
    end
    pending_delete = nil
    if dynamic.status_kind() == "delete_confirm" then
        dynamic.clear_status()
        if refresh and has_active_input(context) then
            context:refresh_non_confirmed_composition()
        end
    end
end

local function processor(key_event, env)
    if key_event:release() then
        return kNoop
    end

    local context = env.engine.context
    if key_event:alt() or core.mode then
        clear_transient_status(context, true)
        cancel_delete_confirmation(context, true)
        return kNoop
    end

    local active_input = has_active_input(context)
    if active_input and is_undo_shortcut(key_event) then
        clear_transient_status(context, false)
        cancel_delete_confirmation(context, false)
        local ok, err = store.undo()
        if ok then
            dynamic.invalidate()
            dynamic.set_status(
                context.input, "〔已撤销上一次调频〕", "transient")
            context:refresh_non_confirmed_composition()
        else
            show_error(context, err)
        end
        return kAccepted
    elseif active_input and is_history_shortcut(key_event) then
        clear_transient_status(context, false)
        cancel_delete_confirmation(context, false)
        local last = store.last_history()
        dynamic.set_status(
            context.input, last and "〔最近操作：" .. last .. "〕"
                or "〔暂无操作历史〕", "transient")
        context:refresh_non_confirmed_composition()
        return kAccepted
    elseif key_event:ctrl() or key_event:super() then
        clear_transient_status(context, true)
        cancel_delete_confirmation(context, true)
        return kNoop
    end

    local keycode = key_event.keycode
    if not keycode or keycode < 0x30 or keycode > 0x39 then
        clear_transient_status(context, true)
        cancel_delete_confirmation(context, true)
        return kNoop
    end
    local action = action_names[string.char(keycode)]
    if not action then
        clear_transient_status(context, true)
        cancel_delete_confirmation(context, true)
        return kNoop
    end

    clear_transient_status(context, false)
    if not context:has_menu() or context.input == "" then
        cancel_delete_confirmation(context, false)
        return kNoop
    end
    local candidate = context:get_selected_candidate()
    if not candidate or not candidate.text or candidate.text == "" then
        cancel_delete_confirmation(context, false)
        return kNoop
    end
    local identity = candidate_identity(candidate)
    local delete_key = table.concat({
        context.input,
        candidate.text,
        identity or "",
    }, "\t")
    if action == "delete" and pending_delete ~= delete_key then
        pending_delete = delete_key
        dynamic.set_status(
            context.input, "〔再次按0确认删除，Esc取消〕",
            "delete_confirm")
        context:refresh_non_confirmed_composition()
        return kAccepted
    end
    if action ~= "delete" then
        cancel_delete_confirmation(context, false)
    else
        dynamic.clear_status()
    end
    local composition = context.composition
    local segment = composition and not composition:empty()
        and composition:back() or nil
    local selected_index = segment and segment.selected_index or 0

    local called, ok, err, focus_input = pcall(
        adjust, action, context, candidate.text, context.input, identity)
    if not called then
        pending_delete = nil
        write_error(action, candidate.text, context.input, ok)
        show_error(context, ok)
        return kAccepted
    elseif not ok then
        pending_delete = nil
        write_error(action, candidate.text, context.input, err)
        show_error(context, err)
        return kAccepted
    end

    pending_delete = nil
    dynamic.clear_status()
    if action == "promote" then
        local hint = upper_level_hint(focus_input, candidate.text)
        if hint then
            dynamic.set_status(focus_input, hint, "transient")
        end
    end
    refresh_after_adjust(
        context, action, candidate.text, selected_index, focus_input)
    return kAccepted
end

local function init(env)
    pending_delete = nil
    dynamic.clear_status()
    store.ensure_runtime_files()
    env.commit_connection =
        env.engine.context.commit_notifier:connect(function()
            pending_delete = nil
            dynamic.clear_status()
        end)
end

return { init = init, func = processor }
