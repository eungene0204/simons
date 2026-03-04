import re
with open('components/strategy/steps/Step1Universe.tsx') as f:
    text = f.read()

lines = text.split('\n')
stack = []
for i, line in enumerate(lines):
    # Find all <div and </div>
    idx = 0
    while idx < len(line):
        o = line.find('<div', idx)
        c = line.find('</div', idx)
        if o != -1 and (c == -1 or o < c):
            # check self-closing like <div ... />
            end_tag = line.find('>', o)
            if end_tag != -1 and line[end_tag-1] == '/':
                idx = end_tag + 1
                continue
            stack.append((i+1, line.strip()))
            idx = o + 4
        elif c != -1 and (o == -1 or c < o):
            if stack:
                stack.pop()
            else:
                print(f"Extra closing div at line {i+1}")
            idx = c + 6
        else:
            break

for s in stack:
    print(f"Unclosed open div from line {s[0]}: {s[1]}")
