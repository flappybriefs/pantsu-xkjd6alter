local kAccepted = 1
local kNoop = 2
local topup_common = require("pantsu.pantsu_topup_common")

local function processor(key_event, env)
    if key_event:release() or key_event:ctrl() or key_event:alt() then
        return kNoop
    end

    local ch = key_event.keycode
    if ch < 0x20 or ch >= 0x7f then
        return kNoop
    end

    local key = string.char(ch)
    if not env.alphabet[key] then
        return kNoop
    end
    if env.topup_set[key] then
        return kNoop
    end

    local context = env.engine.context
    local input = context.input or ""
    if input == "" or topup_common.is_command_input(input) then
        return kNoop
    end

    local previous = input:sub(-1)
    if env.topup_set[previous] then
        return kNoop
    end

    if not context:get_selected_candidate() then
        return kNoop
    end

    context:push_input(key)
    if context:get_selected_candidate() then
        return kAccepted
    end

    context:pop_input(1)
    context:commit()
    context:push_input(key)
    return kAccepted
end

local function init(env)
    local config = env.engine.schema.config
    env.alphabet =
        topup_common.string_to_set(config:get_string("speller/alphabet"))
    env.topup_set =
        topup_common.string_to_set(config:get_string("topup/topup_with"))
end

return { init = init, func = processor }
