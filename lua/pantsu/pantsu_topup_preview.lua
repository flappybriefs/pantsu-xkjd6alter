local store = require("pantsu.pantsu_store")
local topup_common = require("pantsu.pantsu_topup_common")

local M = {}

local function exact_active_entry(code)
    for _, entry in ipairs(store.entries(code)) do
        if entry.active and entry.code == code then
            return entry
        end
    end
    return nil
end

local function has_exact_active_entry(code)
    return exact_active_entry(code) ~= nil
end

local function compose(input, topup_set)
    local prefix, suffix = topup_common.trailing_parts(input, topup_set)
    if not prefix or not suffix then
        return nil
    end
    if has_exact_active_entry(input) then
        return nil
    end

    local prefix_entry = exact_active_entry(prefix)
    if not prefix_entry then
        return nil
    end

    local words = { prefix_entry.word }
    local codes = { prefix }
    for i = 1, #suffix do
        local key = suffix:sub(i, i)
        local entry = exact_active_entry(key)
        if not entry then
            return nil
        end
        words[#words + 1] = entry.word
        codes[#codes + 1] = key
    end
    return table.concat(words, ""), table.concat(codes, "+")
end

function M.func(input, env)
    local context = env.engine.context
    local typed = context.input or ""
    if #typed >= 3 and not topup_common.is_command_input(typed) then
        local word, code = compose(typed, env.topup_set)
        if word then
            local candidate =
                Candidate("pantsu_topup_preview", 0, #typed, word, "顶功")
            candidate.quality = 999998 - #typed
            yield(candidate)
        end
    end

    for candidate in input:iter() do
        yield(candidate)
    end
end

function M.init(env)
    local config = env.engine.schema.config
    env.topup_set =
        topup_common.string_to_set(config:get_string("topup/topup_with"))
end

return M
