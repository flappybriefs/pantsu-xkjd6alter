local M = {}

M.map = nil
M.loaded_path = nil
M.candidate_limit = 7

local function data_path(path)
    if string.sub(path, 1, 1) == "/" then
        return path
    end
    if rime_api and rime_api.get_user_data_dir then
        return rime_api.get_user_data_dir() .. "/" .. path
    end
    return path
end

local function load_map()
    local path = data_path("opencc/pantsu_es.txt")
    if M.map and M.loaded_path == path then
        return M.map
    end

    local map = {}
    local file = io.open(path, "r")
    if file then
        for line in file:lines() do
            local source, target = string.match(line, "^([^\t]+)\t(.+)$")
            if source and target and source ~= "" and target ~= "" then
                local text = target
                if string.sub(target, 1, string.len(source)) == source then
                    text = string.sub(target, string.len(source) + 1)
                end
                local values = {}
                local seen = {}
                for value in string.gmatch(text, "%S+") do
                    if value ~= source and not seen[value] then
                        seen[value] = true
                        table.insert(values, value)
                    end
                end
                if #values > 0 then
                    map[source] = values
                end
            end
        end
        file:close()
    end
    M.map = map
    M.loaded_path = path
    return map
end

function M.func(input, env)
    local context = env and env.engine and env.engine.context
    if not context or not context:get_option("show_es") then
        for candidate in input:iter() do
            yield(candidate)
        end
        return
    end

    local map = load_map()
    local index = 0
    local limit = tonumber(M.candidate_limit) or 7
    for candidate in input:iter() do
        index = index + 1
        yield(candidate)
        local values = index <= limit and map[candidate.text] or nil
        for _, value in ipairs(values or {}) do
            yield(Candidate(
                "pantsu_lazy_emoji",
                candidate.start,
                candidate._end,
                value,
                candidate.text))
        end
    end
end

return M
