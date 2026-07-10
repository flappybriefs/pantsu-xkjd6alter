--[[
single_char_filter: 候选项重排序，使单字优先

此模块默认不在 pantsu.schema.yaml 的 filters 中启用。
--]]

local function filter(input)
    local later = {}
    for candidate in input:iter() do
        if utf8.len(candidate.text) == 1 then
            yield(candidate)
        else
            table.insert(later, candidate)
        end
    end
    for _, candidate in ipairs(later) do
        yield(candidate)
    end
end

return filter
