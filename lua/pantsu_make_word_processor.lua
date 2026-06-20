local core = require("pantsu_make_word_core")
local dynamic = require("pantsu_dynamic")
local profiler = require("pantsu_profiler")
local store = require("pantsu_store")

local kAccepted = 1
local kNoop = 2

local function is_empty_context(context)
    return context.input == ""
end

local function string_to_set(text)
    local result = {}
    for index = 1, string.len(text or "") do
        result[string.sub(text, index, index)] = true
    end
    return result
end

local function event_key(key_event)
    local repr = key_event:repr()
    local code = key_event.keycode
    if code and code >= 0x20 and code < 0x7f then
        return repr, string.char(code)
    end
    return repr, nil
end

local function show_status(context, marker)
    context:clear()
    context.input = marker or "["
end

local function should_topup(context, ch, env)
    local input = context.input
    if input == "" or input == "[" or not ch or not env.alphabet[ch] then
        return false
    end

    local first = string.sub(input, 1, 1)
    local previous = string.sub(input, -1)
    local is_topup = env.topup_set[ch] or false
    local previous_is_topup = env.topup_set[previous] or false
    if env.topup_command and env.topup_set[first] then
        return false
    end

    local min_length = env.topup_min
    if context:get_option("danzi_mode") then
        min_length = env.topup_min_danzi
    end
    return (previous_is_topup and not is_topup)
        or (not previous_is_topup and not is_topup
            and string.len(input) >= min_length)
        or string.len(input) >= env.topup_max
end

local function capture_selected_candidate(context)
    if not context:has_menu() then
        return false
    end
    local candidate = context:get_selected_candidate()
    if not candidate or not candidate.text or candidate.text == "" then
        return false
    end

    core.append(candidate.text, context.input)
    core.prepare_preview()
    return true
end

local function finish_word(context, env, marker)
    local performance = profiler.start(
        "make_word_save",
        core.target_code or "-", core.buffer)
    local code, word, err, moved_entries =
        core.confirm(performance)
    if code and word and word ~= "" then
        if moved_entries and #moved_entries > 0 then
            dynamic.refresh_entries(moved_entries, 4)
        end
        for _, added_code in ipairs(
            core.last_refresh_codes or core.last_codes or { code }) do
            dynamic.refresh_codes({ added_code }, { word }, 4)
        end
        performance:mark("dynamic_refresh")
        env.engine:commit_text(word)
        context:clear()
        performance:mark("commit_and_clear")
        performance:finish("ok")
        return true
    end
    show_status(context, marker)
    performance:mark("error_display")
    performance:finish("failed", tostring(err))
    return false, err
end

local function processor(key_event, env)
    if key_event:release() or key_event:ctrl()
        or key_event:alt() or key_event:super() then
        return kNoop
    end

    local context = env.engine.context
    local key, ch = event_key(key_event)

    if core.mode then
        if key == "space" then
            if context.input == "[" then
                if core.buffer ~= "" then
                    finish_word(context, env, "[")
                    return kAccepted
                elseif context:has_menu() then
                    core.cancel()
                    return kNoop
                else
                    core.cancel()
                    context:clear()
                    return kAccepted
                end
            end

            if context:has_menu() then
                if capture_selected_candidate(context) then
                    show_status(context, "[")
                    return kAccepted
                end
            end

            return kNoop
        end

        if context.input == "[" then
            if key == "Escape" then
                core.cancel()
                context:clear()
                return kAccepted
            end

            if key == "BackSpace" or key == "Backspace" then
                if core.buffer ~= "" then
                    core.backspace_buffer()
                    core.prepare_preview()
                    show_status(context, "[")
                else
                    core.cancel()
                    context:clear()
                end
                return kAccepted
            end

            if core.buffer == "" and context:has_menu()
                and ((ch and string.match(ch, "^%d$"))
                    or key == "Return" or key == "KP_Enter") then
                core.cancel()
                return kNoop
            end

            if ch and string.match(ch, "^[a-z;`]$") then
                context:clear()
                return kNoop
            end

            if ch and string.len(ch) == 1 then
                core.cancel()
                context:clear()
                return kNoop
            end
        end

        if should_topup(context, ch, env)
            and capture_selected_candidate(context) then
            context:clear()
            return kNoop
        end

        if key == "Escape" and is_empty_context(context) then
            core.cancel()
            return kAccepted
        end

        if (key == "BackSpace" or key == "Backspace") and is_empty_context(context) then
            if core.buffer ~= "" then
                core.backspace_buffer()
                return kAccepted
            end
            core.cancel()
            return kAccepted
        end

        return kNoop
    end

    if ch == "[" then
        local target_code =
            not is_empty_context(context) and context.input or nil
        core.start(target_code)
        show_status(context, "[")
        return kAccepted
    end

    return kNoop
end

local function init(env)
    store.ensure_runtime_files()
    core.restore_self_words()
    local config = env.engine.schema.config
    env.topup_set = string_to_set(config:get_string("topup/topup_with"))
    env.alphabet = string_to_set(config:get_string("speller/alphabet"))
    env.topup_min = config:get_int("topup/min_length")
    env.topup_min_danzi =
        config:get_int("topup/min_length_danzi") or env.topup_min
    env.topup_max = config:get_int("topup/max_length")
    env.topup_command = config:get_bool("topup/topup_command") or false

    core.load_words()
    core.load_char_codes()
end

local function fini(env)
end

return { init = init, func = processor, fini = fini }
