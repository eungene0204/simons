import re
text = open('components/strategy/steps/Step1Universe.tsx').read()
div_opens = len(re.findall(r'<div\b', text))
div_closes = len(re.findall(r'</div>', text))
print(f"Open: {div_opens}, Closes: {div_closes}")

