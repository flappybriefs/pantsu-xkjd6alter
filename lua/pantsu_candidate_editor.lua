local core = require("pantsu_make_word_core")
local dynamic = require("pantsu_dynamic")
local profiler = require("pantsu_profiler")
local store = require("pantsu_store")
local chain = require("pantsu_chain")
local usage = require("pantsu_usage")

local kAccepted = 1
local kNoop = 2
local action_names = {
    ["8"] = "promote",
    ["9"] = "demote",
    ["0"] = "delete",
}
local pending_delete = nil
local history_mode = false

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
    if is_macos() then
        return not key_event:shift()
    end
    -- Hamster sends Control+h. Keep Control+Shift+h compatible with
    -- desktop Linux/Windows configurations as well.
    return true
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

local function can_compact(entry, target_code)
    return string.len(target_code) >= word_min_code_length(entry.word)
end

local function promote(model, entry)
    if string.len(entry.code) <= word_min_code_length(entry.word) then
        return nil, "word_code_too_short"
    end
    local source_code = entry.code
    local target_code = string.sub(source_code, 1, string.len(source_code) - 1)
    chain.detach(model, entry)

    local blocked = chain.occupants(model, target_code)
    if #blocked > 0 then
        local visiting = {}
        for _, occupant in ipairs(blocked) do
            local ok, err = chain.push_down(
                model, occupant, "candidate_edit",
                core.full_codes_for_word, visiting)
            if not ok then
                return nil, err
            end
        end
    end
    chain.attach_to_code(model, entry, target_code)
    local compacted = chain.compact_gap(
        model, source_code, can_compact, usage.choose_candidate)
    return true, nil, #compacted
end

local function demote(model, entry)
    local source_code = entry.code
    local target_code, err = core.next_code_for_word(entry.word, entry.code)
    if not target_code then
        return nil, err
    end
    chain.detach(model, entry)

    local blocked = chain.occupants(model, target_code)
    if #blocked == 1 then
        chain.push_down(
            model, blocked[1], "candidate_edit",
            core.full_codes_for_word, {})
    end
    chain.attach_to_code(model, entry, target_code)
    local function can_fill_demote_gap(candidate, gap)
        return candidate ~= entry and can_compact(candidate, gap)
    end
    local compacted = chain.compact_gap(
        model, source_code, can_fill_demote_gap, usage.choose_candidate)
    return true, nil, #compacted
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

local function move_same_code(context, model, entry, direction, profile)
    local words = same_code_candidate_words(context, model, entry.code)
    if profile then
        profile:mark("same_code_candidates")
    end
    for index, word in ipairs(words) do
        local target = direction == "promote" and index - 1 or index + 1
        if word == entry.word and target >= 1 and target <= #words then
            if not store.begin(
                direction, entry.code, entry.word, profile) then
                return false
            end
            words[index], words[target] = words[target], words[index]
            local ok = dynamic.set_same_code_order(entry.code, words)
            if ok then
                local recorded = store.record_order(
                    direction, entry.code, entry.word, profile)
                if not recorded then
                    store.rollback_pending()
                    dynamic.invalidate()
                    return false
                end
            else
                store.rollback_pending()
                dynamic.invalidate()
            end
            return ok
        end
    end
    return false
end

local function delete_entry(model, entry)
    local source_code = entry.code
    chain.detach(model, entry)
    local compacted = chain.compact_gap(
        model, source_code, can_compact, usage.choose_candidate)
    return true, nil, #compacted
end

local function adjust(action, context, word, input, candidate_id, profile)
    local root = input
    local model = chain.load(store, root, profile)
    local entry, err = chain.locate_entry(
        model, word, input, candidate_id)
    if profile then
        profile:mark("entry_locate")
    end
    if not entry then
        return nil, err
    end

    if action == "promote" and entry.code == input
        and string.len(input) > 1 then
        root = string.sub(input, 1, string.len(input) - 1)
        model = chain.load(store, root, profile)
        entry, err = chain.locate_entry(
            model, word, input, candidate_id)
        if profile then
            profile:mark("parent_entry_locate")
        end
        if not entry then
            return nil, err
        end
    end

    local ok
    local compacted
    if action == "promote" then
        if move_same_code(
            context, model, entry, "promote", profile) then
            return true, nil, input
        end
        ok, err, compacted = promote(model, entry)
    elseif action == "demote" then
        ok, err, compacted = demote(model, entry)
        if not ok and err == "no_longer_code"
            and move_same_code(
                context, model, entry, "demote", profile) then
            return true, nil, input
        end
    else
        ok, err, compacted = delete_entry(model, entry)
    end
    if not ok then
        return nil, err
    end
    if profile then
        if compacted and profile.count then
            profile:count("gap_compaction_moves", compacted)
        end
        if action == "promote" or action == "demote"
            or action == "delete" then
            profile:mark("gap_compaction")
        end
        profile:mark("chain_mutation")
    end

    if not store.begin(action, input, word, profile) then
        return nil, "backup_failed"
    end
    ok, err = store.commit(
        model.entries, action, input, word, false, profile)
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
    dynamic.refresh_entries(model.entries, dynamic_root, profile)
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
    backup_missing = "〔保存失败：撤销点丢失〕",
    backup_rotate_failed = "〔保存失败：历史快照写入失败〕",
    backup_history_failed = "〔保存失败：历史记录写入失败〕",
    nothing_to_undo = "〔暂无可撤销操作〕",
    undo_restore_failed = "〔撤销失败：快照读取失败〕",
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

local function history_status(items)
    if #items == 0 then
        return "〔暂无可撤销操作〕"
    end
    local parts = {}
    for index, item in ipairs(items) do
        table.insert(parts, tostring(index) .. item.label)
    end
    return "〔" .. table.concat(parts, "；") .. "；按序号撤销〕"
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
    env.pending_usage = usage.capture_selection(
        context, key_event, env.usage_page_size)
    if key_event:alt() or core.mode then
        clear_transient_status(context, true)
        cancel_delete_confirmation(context, true)
        return kNoop
    end

    local active_input = has_active_input(context)
    if active_input and is_undo_shortcut(key_event) then
        history_mode = false
        clear_transient_status(context, false)
        cancel_delete_confirmation(context, false)
        local ok, err = store.undo()
        if ok then
            local restored, restore_err = core.restore_self_words()
            if not restored and restore_err then
                show_error(context, restore_err)
                return kAccepted
            end
            dynamic.invalidate()
            dynamic.set_status(
                context.input, "〔已撤销上一次操作〕", "transient")
            context:refresh_non_confirmed_composition()
        else
            show_error(context, err)
        end
        return kAccepted
    elseif active_input and is_history_shortcut(key_event) then
        clear_transient_status(context, false)
        cancel_delete_confirmation(context, false)
        local items = store.undo_items()
        history_mode = #items > 0
        dynamic.set_status(
            context.input, history_status(items), "history")
        context:refresh_non_confirmed_composition()
        return kAccepted
    elseif key_event:ctrl() or key_event:super() then
        clear_transient_status(context, true)
        cancel_delete_confirmation(context, true)
        return kNoop
    end

    local keycode = key_event.keycode
    if history_mode and keycode and keycode >= 0x31 and keycode <= 0x37 then
        local index = keycode - 0x30
        local items = store.undo_items()
        if index <= #items then
            local ok, err = store.undo(index)
            history_mode = false
            if ok then
                local restored, restore_err = core.restore_self_words()
                if not restored and restore_err then
                    show_error(context, restore_err)
                    return kAccepted
                end
                dynamic.invalidate()
                dynamic.set_status(
                    context.input,
                    "〔已撤销至第" .. tostring(index) .. "步之前〕",
                    "transient")
                context:refresh_non_confirmed_composition()
            else
                show_error(context, err)
            end
            return kAccepted
        end
    end
    if history_mode then
        history_mode = false
        if dynamic.status_kind() == "history" then
            dynamic.clear_status()
            context:refresh_non_confirmed_composition()
        end
    end
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

    local performance = profiler.start(
        action, context.input, candidate.text)
    local called, ok, err, focus_input = pcall(
        adjust, action, context, candidate.text, context.input,
        identity, performance)
    if not called then
        pending_delete = nil
        show_error(context, ok)
        performance:finish("error", tostring(ok))
        return kAccepted
    elseif not ok then
        pending_delete = nil
        show_error(context, err)
        performance:finish("failed", tostring(err))
        return kAccepted
    end

    pending_delete = nil
    dynamic.clear_status()
    if action == "promote" then
        local hint = upper_level_hint(focus_input, candidate.text)
        performance:mark("upper_level_hint")
        if hint then
            dynamic.set_status(focus_input, hint, "transient")
        end
    end
    refresh_after_adjust(
        context, action, candidate.text, selected_index, focus_input)
    performance:mark("candidate_refresh")
    performance:finish("ok")
    return kAccepted
end

local function init(env)
    pending_delete = nil
    history_mode = false
    dynamic.clear_status()
    env.pending_usage = nil
    env.usage_page_size = 7
    local schema = env.engine.schema
    if schema and schema.config and schema.config.get_int then
        env.usage_page_size =
            schema.config:get_int("menu/page_size")
            or env.usage_page_size
    end
    env.commit_connection =
        env.engine.context.commit_notifier:connect(function(context)
            if usage.commit_matches(context, env.pending_usage) then
                usage.record_selection(
                    env.pending_usage.word,
                    env.pending_usage.input)
            end
            env.pending_usage = nil
            pending_delete = nil
            history_mode = false
            dynamic.clear_status()
        end)
end

return { init = init, func = processor }
