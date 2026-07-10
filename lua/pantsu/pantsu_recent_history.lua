local M = {}

local DEFAULT_INPUT = ";;"
local DEFAULT_SIZE = 5
local MAX_SIZE = 9
local history = {}

local function config_string(env, path, default)
    local config = env and env.engine and env.engine.schema
        and env.engine.schema.config
    if not config or not config.get_string then
        return default
    end
    local ok, value = pcall(function()
        return config:get_string(path)
    end)
    if ok and type(value) == "string" and value ~= "" then
        return value
    end
    return default
end

local function config_size(env)
    local config = env and env.engine and env.engine.schema
        and env.engine.schema.config
    local value
    if config and config.get_int then
        local ok, result = pcall(function()
            return config:get_int("recent_history/size")
        end)
        if ok then
            value = tonumber(result)
        end
    end
    value = math.floor(value or DEFAULT_SIZE)
    return math.max(1, math.min(MAX_SIZE, value))
end

local function remember(text, size)
    if type(text) ~= "string" or text == "" then
        return false
    end
    for index = #history, 1, -1 do
        if history[index] == text then
            table.remove(history, index)
        end
    end
    table.insert(history, 1, text)
    while #history > size do
        table.remove(history)
    end
    return true
end

local function contains(text)
    for index = 1, #history do
        if history[index] == text then
            return true
        end
    end
    return false
end

local function disconnect(connection)
    if connection and connection.disconnect then
        pcall(function() connection:disconnect() end)
    end
end

function M.init(env)
    local context = env and env.engine and env.engine.context
    if not context then
        return
    end
    env.history_trigger = config_string(
        env, "recent_history/input", DEFAULT_INPUT
    )
    env.history_size = config_size(env)
    env.history_last_input = context.input or ""
    env.history_replay_armed = false

    if context.update_notifier and context.update_notifier.connect then
        env.history_update_connection = context.update_notifier:connect(
            function(current)
                current = current or context
                env.history_last_input = current.input or ""
                if env.history_last_input ~= ""
                    and env.history_last_input ~= env.history_trigger then
                    env.history_replay_armed = false
                end
            end
        )
    end
    if context.commit_notifier and context.commit_notifier.connect then
        env.history_commit_connection = context.commit_notifier:connect(
            function(current)
                current = current or context
                if current.get_commit_text then
                    local ok, text = pcall(function()
                        return current:get_commit_text()
                    end)
                    local replay = ok and contains(text)
                        and (env.history_replay_armed
                            or env.history_last_input == env.history_trigger)
                    if ok and not replay then
                        remember(text, env.history_size)
                    end
                end
                env.history_last_input = ""
                env.history_replay_armed = false
            end
        )
    end
end

function M.func(input, segment, env)
    local trigger = env.history_trigger
        or config_string(env, "recent_history/input", DEFAULT_INPUT)
    if input ~= trigger then
        return
    end
    local size = env.history_size or config_size(env)
    env.history_replay_armed = true
    for index = 1, math.min(size, #history) do
        local candidate = Candidate(
            "history",
            segment.start,
            segment._end,
            history[index],
            "〔历史" .. tostring(index) .. "〕"
        )
        candidate.quality = 10000 - index
        yield(candidate)
    end
end

function M.fini(env)
    disconnect(env.history_update_connection)
    disconnect(env.history_commit_connection)
    env.history_update_connection = nil
    env.history_commit_connection = nil
    env.history_replay_armed = false
end

return M
