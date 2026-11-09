# Private parser output: listener metadata and the first inbound account only.
# The caller stores this in root-only RAM files; nodes and arbitrary YAML are excluded.
require 'yaml'
path = ARGV.fetch(0)
raise 'profile too large' if File.size(path) > 8 * 1024 * 1024
data = YAML.safe_load(File.read(path), permitted_classes: [], permitted_symbols: [], aliases: true)
raise 'invalid profile' unless data.is_a?(Hash)
out = {}
%w[port socks-port mixed-port redir-port tproxy-port].each { |key| out[key] = data[key] }
out['dns'] = (data['dns'].is_a?(Hash) ? data['dns'] : {}).slice('enable', 'listen')
out['tun'] = (data['tun'].is_a?(Hash) ? data['tun'] : {}).slice('enable', 'device')
out['authentication'] = Array(data['authentication']).take(1)
out['listeners'] = Array(data['listeners']).take(64).map { |row| row.is_a?(Hash) ? row.slice('name', 'type', 'port', 'device', 'udp', 'users') : {} }
def encode_json(value)
  case value
  when Hash
    '{' + value.map { |key, item| encode_json(key.to_s) + ':' + encode_json(item) }.join(',') + '}'
  when Array
    '[' + value.map { |item| encode_json(item) }.join(',') + ']'
  when String
    '"' + value.gsub(/["\\\x00-\x1f]/) { |char| ['"', '\\'].include?(char) ? '\\' + char : format('\\u%04x', char.ord) } + '"'
  when Integer then value.to_s
  when TrueClass then 'true'
  when FalseClass then 'false'
  when NilClass then 'null'
  else raise 'unsupported listener metadata'
  end
end
puts encode_json(out)
