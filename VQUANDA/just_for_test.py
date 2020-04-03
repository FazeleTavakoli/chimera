import re


inputString = "Element <literal> with attributes {'xml:lang': 'en'}, children [] and cdata Nakkertok 11 ewryue"
pattern = re.compile(r'(cdata) ((\d+)|((\w+)(\s*))+)')
matchObj = re.search(pattern, inputString)
matched_titles = pattern.finditer(inputString)
for match in matched_titles:
    title = match.group(2)


###################

