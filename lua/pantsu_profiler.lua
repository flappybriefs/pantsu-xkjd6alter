local M = {}

M.config_file = "pantsu_performance.enabled"
M.log_file = "pantsu_performance.tsv"
M.default_limit = 300

local function data_path(path)
    if string.sub(path, 1, 1) == "/" then
        return path
    end
    if rime_api and rime_api.get_user_data_dir then
        return rime_api.get_user_data_dir() .. "/" .. path
    end
    return path
end

local function read_lines(path)
    local lines = {}
    local file = io.open(data_path(path), "r")
    if not file then
        return lines
    end
    for line in file:lines() do
        if line ~= "" then
            table.insert(lines, line)
        end
    end
    file:close()
    return lines
end

local function verified_write(path, lines)
    local target = data_path(path)
    local temp = target .. ".tmp"
    local content = #lines > 0 and table.concat(lines, "\n") .. "\n" or ""
    local file = io.open(temp, "wb")
    if not file then
        return false
    end
    file:write(content)
    if not file:close() then
        os.remove(temp)
        return false
    end
    local renamed = os.rename and os.rename(temp, target)
    if not renamed then
        os.remove(temp)
        file = io.open(target, "wb")
        if not file then
            return false
        end
        file:write(content)
        if not file:close() then
            return false
        end
    end
    local check = io.open(target, "rb")
    if not check then
        return false
    end
    local saved = check:read("*a")
    check:close()
    return saved == content
end

local function settings()
    local enabled = true
    local limit = M.default_limit
    local file = io.open(data_path(M.config_file), "r")
    if not file then
        verified_write(M.config_file, {
            "enabled\t1",
            "limit\t" .. tostring(limit),
            "clock\tlua_cpu_ms",
        })
        return enabled, limit
    end
    for line in file:lines() do
        local key, value = string.match(line, "^([^\t]+)\t(.+)$")
        if key == "enabled" then
            enabled = value ~= "0"
        elseif key == "limit" then
            limit = math.max(10, tonumber(value) or limit)
        end
    end
    file:close()
    return enabled, limit
end

local function installation_id()
    local file = io.open(data_path("installation.yaml"), "r")
    if not file then
        return "unknown"
    end
    for line in file:lines() do
        local value = string.match(line, "^installation_id:%s*(.+)")
        if value then
            file:close()
            return value
        end
    end
    file:close()
    return "unknown"
end

local Profile = {}
Profile.__index = Profile

function Profile:mark(name)
    if not self.enabled then
        return
    end
    local now = os.clock()
    table.insert(self.steps, {
        name = name,
        elapsed = (now - self.last) * 1000,
    })
    self.last = now
end

function Profile:finish(status, detail)
    if not self.enabled or self.finished then
        return
    end
    self:mark("total")
    self.finished = true
    local parts = {}
    local total = 0
    for _, step in ipairs(self.steps) do
        if step.name ~= "total" then
            total = total + step.elapsed
            table.insert(parts,
                step.name .. "=" .. string.format("%.3f", step.elapsed))
        end
    end
    local lines = read_lines(M.log_file)
    if #lines == 0 or not string.match(lines[1], "^version\t") then
        lines = {
            "version\t1\tclock\tlua_cpu_ms"
                .. "\tnote\trecording_overhead_excluded",
        }
    end
    table.insert(lines, table.concat({
        tostring(os.time()),
        installation_id(),
        self.action or "-",
        self.input or "-",
        self.word or "-",
        status or "ok",
        string.format("%.3f", total),
        table.concat(parts, ";"),
        detail or "-",
    }, "\t"))
    while #lines > self.limit + 1 do
        table.remove(lines, 2)
    end
    verified_write(M.log_file, lines)
end

function M.start(action, input, word)
    local enabled, limit = settings()
    local now = os.clock()
    return setmetatable({
        enabled = enabled,
        limit = limit,
        action = action,
        input = input,
        word = word,
        started = now,
        last = now,
        steps = {},
        finished = false,
    }, Profile)
end

return M
