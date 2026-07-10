local M = {}

local function title_case(word)
    return string.upper(string.sub(word, 1, 1)) .. string.sub(word, 2)
end

local function has_prefix(word, env)
    if env.prefix_memory_unavailable then
        return nil
    end
    if not env.prefix_memory then
        local ok, memory = pcall(function()
            return Memory(env.engine, Schema("pantsu.en"))
        end)
        if not ok or not memory then
            env.prefix_memory_unavailable = true
            return nil
        end
        env.prefix_memory = memory
    end
    local ok, found = pcall(function()
        return env.prefix_memory:dict_lookup(word, true, 1)
    end)
    if not ok then
        return nil
    end
    return found and true or false
end

function M.func(_, segment, env)
    if not segment:has_tag("pantsuen") then
        return
    end
    local word = string.match(env.engine.context.input or "", "^%]([a-z]+)$")
    if not word or has_prefix(word, env) ~= false then
        return
    end

    local lower = string.lower(word)
    yield(Candidate(
    "pantsu_english_fallback", segment.start, segment._end, lower, ""))
    yield(Candidate(
        "pantsu_english_fallback", segment.start, segment._end,
        title_case(lower), ""))
end

function M.fini(env)
    if env.prefix_memory then
        pcall(function()
            env.prefix_memory:disconnect()
        end)
        env.prefix_memory = nil
    end
end

return M
