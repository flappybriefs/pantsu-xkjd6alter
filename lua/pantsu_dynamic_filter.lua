local dynamic = require("pantsu_dynamic")

local function filter(input, env)
    local context = env.engine.context
    local typed = context.input
    local state = dynamic.match(typed)
    if not state then
        for candidate in input:iter() do
            yield(candidate)
        end
        return
    end

    local yielded = {}
    local has_exact = false
    local has_completion = false
    for _, entry in ipairs(state.entries) do
        if string.sub(entry.code, 1, string.len(typed)) == typed
            and not yielded[entry.word] then
            local remaining = string.sub(entry.code, string.len(typed) + 1)
            local candidate_type = "pantsu_dynamic"
            local comment = ""
            if remaining ~= "" then
                has_completion = true
                candidate_type = "completion"
                comment = "~" .. remaining
            else
                has_exact = true
            end
            local candidate = Candidate(
                candidate_type, 0, string.len(typed), entry.word, comment)
            candidate.quality = 1000000 - string.len(entry.code)
            yield(candidate)
            yielded[entry.word] = true
        end
    end

    if has_exact and not has_completion then
        return
    end

    for candidate in input:iter() do
        if not state.suppress[candidate.text] and not yielded[candidate.text] then
            yield(candidate)
        end
    end
end

return filter
