import re

with open('web_app/templates/index.html', 'r') as f:
    content = f.read()

pattern_nav = r"        // Update topbar title \(strip icon text\)\s*topbarTitle\.textContent = this\.querySelector\('span'\)\.textContent\.trim\(\);\s*}\);\s*}\);"

replacement_nav = """        // Update topbar title (strip icon text)
        topbarTitle.textContent = this.querySelector('span').textContent.trim();
        
        // Save state to localStorage
        localStorage.setItem('forensys_active_section', targetId);
    });
});

// Restore active section on load
document.addEventListener('DOMContentLoaded', () => {
    const savedSection = localStorage.getItem('forensys_active_section');
    if (savedSection) {
        const targetNav = document.querySelector(`.nav-item-custom[data-section="${savedSection}"]`);
        if (targetNav) targetNav.click();
    }
});"""

new_content = re.sub(pattern_nav, replacement_nav, content, flags=re.DOTALL)
with open('web_app/templates/index.html', 'w') as f:
    f.write(new_content)
