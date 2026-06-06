import re
def test(linea):
    linea_limpia = re.sub(r'\d+:\d+', '', linea)
    linea_limpia = re.sub(r'\d+:', '', linea_limpia)
    partes = linea_limpia.split()
    numeros = [p for p in partes if p.isdigit()]
    print(f"Original: {numeros}")
    
    partes_2 = linea.split()
    numeros_2 = [p for p in partes_2 if p.isdigit() and p != '000']
    print(f"New: {numeros_2}")

test("004:  000       0000002048   0030717951   0030715904   Basic data partition")
test("001:  000:000   0000000063   0000204862   0000204800   FAT16 (0x06)")
