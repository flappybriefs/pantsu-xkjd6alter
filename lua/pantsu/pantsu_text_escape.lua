local M = {}

local escapes = {
    n = "\n",
    r = "\r",
    t = "\t",
    ["\\"] = "\\",
}

function M.decode(text)
    if not text or not string.find(text, "\\", 1, true) then
        return text
    end

    local output = {}
    local index = 1
    while index <= #text do
        local current = string.sub(text, index, index)
        if current == "\\" and index < #text then
            local next_char = string.sub(text, index + 1, index + 1)
            local decoded = escapes[next_char]
            if decoded then
                table.insert(output, decoded)
                index = index + 2
            else
                table.insert(output, current)
                index = index + 1
            end
        else
            table.insert(output, current)
            index = index + 1
        end
    end
    return table.concat(output)
end

function M.func(input, _)
    for candidate in input:iter() do
        local decoded = M.decode(candidate.text)
        if decoded ~= candidate.text then
            if ShadowCandidate then
                yield(ShadowCandidate(
                    candidate, candidate.type, decoded, candidate.comment))
            else
                local shadow = Candidate(
                    candidate.type,
                    candidate.start or 0,
                    candidate._end or 0,
                    decoded,
                    candidate.comment or "")
                shadow.quality = candidate.quality
                yield(shadow)
            end
        else
            yield(candidate)
        end
    end
end

return M
