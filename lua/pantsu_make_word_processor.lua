local core = require("pantsu_make_word_core")

local kAccepted = 1
local kNoop = 2

local function is_empty_context(context)
    return context.input == ""
end

local function utf8_len(text)
    return utf8.len(text or "") or 0
end

local function event_key(key_event)
    local repr = key_event:repr()
    local code = key_event.keycode
    if code and code >= 0x20 and code < 0x7f then
        return repr, string.char(code)
    end
    return repr, nil
end

local function show_status(context)
    context:clear()
    context.input = "["
end

local function processor(key_event, env)
    if key_event:release() or key_event:ctrl() or key_event:alt() then
        return kNoop
    end

    local context = env.engine.context
    local key, ch = event_key(key_event)

    if core.mode then
        if key == "space" then
            if context.input == "[" then
                if core.buffer ~= "" then
                    local _, word = core.confirm()
                    if word and word ~= "" then
                        env.engine:commit_text(word)
                    end
                    context:clear()
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
                local cand = context:get_selected_candidate()
                if cand and cand.text and cand.text ~= "" then
                    local code = nil
                    if utf8_len(cand.text) == 1 then
                        code = context.input
                    end
                    core.append(cand.text, code)
                    show_status(context)
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
                    show_status(context)
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

    if ch == "[" and is_empty_context(context) then
        core.start()
        show_status(context)
        return kAccepted
    end

    return kNoop
end

local function init(env)
    core.optimize_self_word_codes()
    core.load_words()
    core.load_char_codes()
end

local function fini(env)
end

return { init = init, func = processor, fini = fini }
