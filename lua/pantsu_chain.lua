local M = {}

local function code_startswith(code, prefix)
    return string.sub(code or "", 1, string.len(prefix or "")) == prefix
end

function M.load(store, input, profile)
    local model = {
        entries = {},
        by_code = {},
        by_word = {},
    }
    for _, entry in ipairs(store.entries(input, profile)) do
        table.insert(model.entries, entry)
        if entry.active then
            if not model.by_code[entry.code] then
                model.by_code[entry.code] = {}
            end
            table.insert(model.by_code[entry.code], entry)
            if not model.by_word[entry.word] then
                model.by_word[entry.word] = {}
            end
            table.insert(model.by_word[entry.word], entry)
        end
    end
    if profile then
        profile:mark("chain_model")
    end
    return model
end

function M.remove_from_code(model, entry)
    local list = model.by_code[entry.code] or {}
    for index = #list, 1, -1 do
        if list[index] == entry then
            table.remove(list, index)
            break
        end
    end
end

function M.attach_to_code(model, entry, code)
    entry.code = code
    entry.active = true
    if not model.by_code[code] then
        model.by_code[code] = {}
    end
    table.insert(model.by_code[code], entry)
end

function M.detach(model, entry)
    M.remove_from_code(model, entry)
    entry.active = false
end

function M.occupants(model, code, options)
    options = options or {}
    local result = {}
    for _, entry in ipairs(model.by_code[code] or {}) do
        local excluded = entry == options.entry
            or (options.word and entry.word == options.word)
        if entry.active and not excluded then
            table.insert(result, entry)
        end
    end
    return result
end

function M.locate_entry(model, word, input, candidate_id)
    if candidate_id and candidate_id ~= "" then
        for _, entry in ipairs(model.entries) do
            if entry.id == candidate_id and entry.active then
                return entry
            end
        end
    end
    local exact
    local best
    local ambiguous = false
    for _, entry in ipairs(model.by_word[word] or {}) do
        if entry.active and code_startswith(entry.code, input) then
            if entry.code == input then
                if exact and exact ~= entry then
                    return nil, "ambiguous_exact_entry"
                end
                exact = entry
            elseif not best or string.len(entry.code) < string.len(best.code) then
                best = entry
                ambiguous = false
            elseif string.len(entry.code) == string.len(best.code) then
                ambiguous = true
            end
        end
    end
    if exact then
        return exact
    end
    if ambiguous then
        return nil, "ambiguous_completion_entry"
    end
    return best, best and nil or "entry_not_found"
end

function M.extension_codes(word, current_code, full_codes_for_word)
    local found = {}
    for _, full_code in ipairs(full_codes_for_word(word)) do
        if string.len(full_code) > string.len(current_code)
            and code_startswith(full_code, current_code) then
            local max_extra = math.min(
                2, string.len(full_code) - string.len(current_code))
            for extra = 1, max_extra do
                found[string.sub(
                    full_code, 1, string.len(current_code) + extra)] = true
            end
        end
    end
    local result = {}
    for code in pairs(found) do
        table.insert(result, code)
    end
    table.sort(result, function(left, right)
        if string.len(left) == string.len(right) then
            return left < right
        end
        return string.len(left) < string.len(right)
    end)
    return result
end

local function move_entry(model, entry, code)
    M.remove_from_code(model, entry)
    M.attach_to_code(model, entry, code)
end

local function make_word_strategy(
    model, entry, choices, visiting, recurse)
    for _, next_code in ipairs(choices) do
        local blocked = M.occupants(
            model, next_code, { word = entry.word })
        local movable = true
        for _, occupant in ipairs(blocked) do
            local ok = recurse(occupant, visiting)
            if not ok then
                movable = false
                break
            end
        end
        if movable then
            move_entry(model, entry, next_code)
            return true
        end
    end
    if choices[1] then
        move_entry(model, entry, choices[1])
        return true
    end
    return nil, "occupied_code_cannot_move:" .. entry.word
end

local function candidate_edit_strategy(
    model, entry, choices, visiting, recurse)
    local groups = {}
    for _, code in ipairs(choices) do
        local length = string.len(code)
        if not groups[length] then
            groups[length] = {}
        end
        table.insert(groups[length], code)
    end
    local lengths = {}
    for length in pairs(groups) do
        table.insert(lengths, length)
    end
    table.sort(lengths)

    local last_error
    for _, length in ipairs(lengths) do
        local group = groups[length]
        if #group == 1 then
            local next_code = group[1]
            local blocked = M.occupants(
                model, next_code, { entry = entry })
            if #blocked == 1 then
                recurse(blocked[1], visiting)
            end
            move_entry(model, entry, next_code)
            return true
        end
        last_error = "ambiguous_full_code:" .. entry.word
    end
    return nil, last_error or ("no_available_code:" .. entry.word)
end

local strategies = {
    make_word = {
        no_choices = function(word)
            return "occupied_code_cannot_move:" .. word
        end,
        apply = make_word_strategy,
    },
    candidate_edit = {
        no_choices = function(word)
            return "no_longer_code:" .. word
        end,
        apply = candidate_edit_strategy,
    },
}

function M.push_down(
    model, entry, policy_name, full_codes_for_word, visiting)
    local policy = strategies[policy_name]
    if not policy then
        return nil, "unknown_chain_policy:" .. tostring(policy_name)
    end
    visiting = visiting or {}
    if visiting[entry] then
        return nil, "code_cycle"
    end
    visiting[entry] = true
    local choices = M.extension_codes(
        entry.word, entry.code, full_codes_for_word)
    if #choices == 0 then
        visiting[entry] = nil
        return nil, policy.no_choices(entry.word)
    end
    local function recurse(next_entry, active_visiting)
        return M.push_down(
            model, next_entry, policy_name,
            full_codes_for_word, active_visiting)
    end
    local ok, err = policy.apply(
        model, entry, choices, visiting, recurse)
    visiting[entry] = nil
    return ok, err
end

function M.compact_gap(model, initial_gap, can_move)
    local gap = initial_gap
    local moved = {}
    local visited = {}
    while gap and gap ~= "" and not visited[gap] do
        visited[gap] = true
        if #M.occupants(model, gap) > 0 then
            break
        end

        local nearest_length
        local candidates = {}
        local seen = {}
        for _, entry in ipairs(model.entries) do
            local code = entry.code or ""
            if entry.active and not seen[entry]
                and string.len(code) > string.len(gap)
                and code_startswith(code, gap)
                and (not can_move or can_move(entry, gap)) then
                seen[entry] = true
                local length = string.len(code)
                if not nearest_length or length < nearest_length then
                    nearest_length = length
                    candidates = { entry }
                elseif length == nearest_length then
                    table.insert(candidates, entry)
                end
            end
        end
        if #candidates ~= 1 then
            break
        end

        local entry = candidates[1]
        local source_code = entry.code
        move_entry(model, entry, gap)
        table.insert(moved, {
            entry = entry,
            from = source_code,
            to = gap,
        })
        gap = source_code
    end
    return moved
end

return M
