local M = {}

function M.string_to_set(str)
    local result = {}
    if type(str) ~= "string" then
        return result
    end
    for i = 1, #str do
        result[str:sub(i, i)] = true
    end
    return result
end

function M.is_command_input(input)
    if type(input) ~= "string" or input == "" then
        return false
    end
    local lead = input:sub(1, 1)
    return lead == "="
        or lead == "\\"
        or lead == "&"
        or lead == "["
        or lead == "]"
        or lead == "'"
        or lead == "/"
        or lead == ";"
end

function M.push_text(context, text)
    if type(text) ~= "string" then
        return
    end
    for i = 1, #text do
        context:push_input(text:sub(i, i))
    end
end

function M.trailing_parts(input, topup_set)
    if type(input) ~= "string" or not topup_set then
        return nil, nil
    end
    local index = #input
    while index > 0 and topup_set[input:sub(index, index)] do
        index = index - 1
    end
    if index == #input or index == 0 then
        return nil, nil
    end
    return input:sub(1, index), input:sub(index + 1)
end

return M
