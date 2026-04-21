import os
import re

template_dir = '/Users/sulabhtharu/Sulabh/Data Science/ResumeRank/resume_ai/templates'

for root, _, files in os.walk(template_dir):
    for f in files:
        if f.endswith('.html'):
            path = os.path.join(root, f)
            with open(path, 'r') as file:
                content = file.read()
            
            orig_content = content
            
            # Form labels / small text: text-[10px] -> text-[11px]
            content = content.replace('text-[10px]', 'text-[11px]')
            
            # Specific label text opacity: text-white/40 or text-white/45 to text-white/70
            # We want to do this safely. Usually they are like `class="... text-white/40 ..."`
            content = content.replace('text-white/40', 'text-white/70')
            content = content.replace('text-white/45', 'text-white/70')
            
            # Placeholders
            content = content.replace('placeholder-white/30', 'placeholder-white/50')
            
            # Also in company_base.html and candidate_base.html, the custom CSS .form-label has 10px, let's bump it
            content = content.replace('font-size: 10px;', 'font-size: 11px;')
            # and section-title has 11px, let's bump to 12px
            content = content.replace('font-size: 11px; text-transform: uppercase;', 'font-size: 12px; text-transform: uppercase;')
            
            # The style block in hr_applications uses rgba(255,255,255,0.40). We can skip it since it's only in prototype.
            
            if orig_content != content:
                with open(path, 'w') as file:
                    file.write(content)
                print(f"Updated {path}")
