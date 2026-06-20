local core = require("pantsu_make_word_core")

local error_messages = {
    write_failed = "〔保存失败：用户词库不可写〕",
    override_write_failed = "〔保存失败：覆盖文件不可写〕",
    self_word_write_failed = "〔保存失败：自造词记录不可写〕",
    too_short = "〔至少需要两个字〕",
    target_code_too_short = "〔当前码短于该词允许的最短码〕",
    backup_failed = "〔保存失败：无法创建撤销点〕",
    backup_missing = "〔保存失败：撤销点丢失〕",
    backup_rotate_failed = "〔保存失败：历史快照写入失败〕",
    backup_history_failed = "〔保存失败：历史记录写入失败〕",
    same_code_order_write_failed = "〔保存失败：同码顺序写入失败〕",
}

local function filter(input, env)
    local context = env.engine.context
    if context.input == "[" then
        if not core.mode then
            core.start(nil)
        end
        if core.buffer == "" then
            for cand in input:iter() do
                yield(cand)
            end
            return
        end
        core.prepare_preview()
        local target = core.target_code
            and "〔保存到 " .. core.target_code .. "〕" or nil
        local mismatch = core.last_error
            and string.match(core.last_error, "^target_code_mismatch:(.+)$")
        local occupied = core.last_error
            and string.match(
                core.last_error, "^occupied_code_cannot_move:(.+)$")
        local comment = core.preview_text
            or mismatch
            and "〔编码不匹配，可用全码：" .. mismatch .. "〕"
            or occupied
                and "〔当前码无法腾位：" .. occupied .. "〕"
            or error_messages[core.last_error]
            or (core.last_error and "〔保存失败：" .. core.last_error .. "〕")
            or target
            or "〔空格保存〕"
        yield(Candidate("pantsu_make_word", 0, 1, core.buffer, comment))
        return
    end

    for cand in input:iter() do
        yield(cand)
    end
end

return filter
