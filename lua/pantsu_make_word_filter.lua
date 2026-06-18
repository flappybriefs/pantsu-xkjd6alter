local core = require("pantsu_make_word_core")

local function filter(input, env)
    local context = env.engine.context
    if context.input == "[" then
        if not core.mode then
            core.start()
        end
        if core.buffer == "" then
            for cand in input:iter() do
                yield(cand)
            end
            return
        end
        yield(Candidate("pantsu_make_word", 0, 1, core.buffer, "〔空格保存〕"))
        return
    end

    for cand in input:iter() do
        yield(cand)
    end
end

return filter
