import sys

p = 'docs/adr/0001-architecture-et-contrat-api.md'
adr = open(p, 'rb').read().decode('utf-8')

def load(f):
    return open(f, 'rb').read().decode('utf-8').split('\n')

L = load(sys.argv[1])
NEW = load(sys.argv[2])
start = adr.index('## Traçabilité critère')
end = adr.index('## Non objectifs de F01')
out = adr[:start] + '\n'.join(NEW) + adr[end:]
open(p, 'wb').write(out.replace('\n', '\r\n').encode('utf-8'))
print('section remplacée')
