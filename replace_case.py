import re

with open('web_app/templates/index.html', 'r') as f:
    content = f.read()

# Add saving logic to loadCaseInUI
pattern_load = r'function loadCaseInUI\(caso, notasTxt\) \{\s*// Cargar datos en el formulario\s*activeCaseNumber = caso\.caso_id;'
replacement_load = r'''function loadCaseInUI(caso, notasTxt) {
    // Cargar datos en el formulario
    activeCaseNumber = caso.caso_id;
    localStorage.setItem('forensys_active_case_path', caso.ruta || '');
'''

# Add clearing logic to resetCaseForm
pattern_reset = r'function resetCaseForm\(\) \{\s*closeHashModal\(\);\s*activeCaseNumber = null;'
replacement_reset = r'''function resetCaseForm() {
    closeHashModal();
    activeCaseNumber = null;
    localStorage.removeItem('forensys_active_case_path');
'''

# Add auto-load logic to DOMContentLoaded (which we just added for sections)
pattern_dom = r"document\.addEventListener\('DOMContentLoaded', \(\) => \{\s*const savedSection = localStorage\.getItem\('forensys_active_section'\);\s*if \(savedSection\) \{\s*const targetNav = document\.querySelector\(`\.nav-item-custom\[data-section=\"\$\{savedSection\}\"\]`\);\s*if \(targetNav\) targetNav\.click\(\);\s*\}\s*\}\);"

replacement_dom = r'''document.addEventListener('DOMContentLoaded', () => {
    const savedSection = localStorage.getItem('forensys_active_section');
    if (savedSection) {
        const targetNav = document.querySelector(`.nav-item-custom[data-section="${savedSection}"]`);
        if (targetNav) targetNav.click();
    }
    
    const savedCasePath = localStorage.getItem('forensys_active_case_path');
    if (savedCasePath) {
        importarCasoDesdeRuta(savedCasePath);
    }
});'''

c1 = re.sub(pattern_load, replacement_load, content)
c2 = re.sub(pattern_reset, replacement_reset, c1)
c3 = re.sub(pattern_dom, replacement_dom, c2)

with open('web_app/templates/index.html', 'w') as f:
    f.write(c3)

