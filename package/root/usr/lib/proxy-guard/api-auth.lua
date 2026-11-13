-- SPDX-License-Identifier: MIT
local fs = require 'nixio.fs'
local M = {}
local directory = '/var/run/proxy-guard'
local path = directory .. '/api-uuid'

local function valid(uuid)
    return type(uuid) == 'string' and #uuid == 36 and
        uuid:match('^%x%x%x%x%x%x%x%x%-%x%x%x%x%-4%x%x%x%-[89ab]%x%x%x%-%x+$') ~= nil
end

function M.current()
    local file = io.open(path, 'r')
    if not file then return nil end
    local uuid = file:read(37)
    file:close()
    if valid(uuid) then return uuid end
end

function M.config()
    local cursor = require('uci').cursor()
    if not cursor:load('/etc/config/proxy_guard') then return nil end
    return cursor:get_all('proxy_guard', 'main')
end

function M.enabled()
    if fs.access(directory .. '/removing') then return false end
    local raw = M.config()
    return raw and raw.api_enabled == '1' or false
end

function M.ready()
    return not fs.access('/etc/proxy-guard/setup/pending.json')
end

function M.bearer()
    return (os.getenv('HTTP_AUTHORIZATION') or ''):match('^[Bb][Ee][Aa][Rr][Ee][Rr] ([%x%-]+)$')
end

function M.matches(candidate)
    if not valid(candidate) or not M.enabled() then return false end
    local current = M.current()
    if not current then return false end
    local difference = 0
    for i = 1, #current do
        difference = difference + math.abs(current:byte(i) - candidate:byte(i))
    end
    return difference == 0
end

-- Called under the setup lock, after applying the API setting.
function M.sync(enabled)
    if not enabled then
        if fs.access(path) then assert(os.remove(path), 'api_uuid_revoke_failed') end
        os.remove(path .. '.new')
        return
    end
    if M.current() then return end
    local uuid = (fs.readfile('/proc/sys/kernel/random/uuid') or ''):match('^(%S+)')
    assert(valid(uuid), 'api_random_unavailable')
    local file = assert(io.open(path .. '.new', 'w'), 'api_uuid_write_failed')
    assert(fs.chmod(path .. '.new', '600'), 'api_uuid_mode_failed')
    assert(file:write(uuid))
    assert(file:close())
    assert(os.rename(path .. '.new', path), 'api_uuid_write_failed')
end

return M
