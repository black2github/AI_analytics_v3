import logging
logging.basicConfig(level=logging.DEBUG)

# Тест для диагностики
from app.filter_approved_fragments import filter_approved_fragments
from app.filter_all_fragments import filter_all_fragments

html = '''
<h1 id="id-[DRAFT]ЭФБанка&quot;Журналзаявок&quot;-КатегорииЭФКатегории">
    <span style="color: rgb(0,51,102);">
        <span class="confluence-anchor-link conf-macro output-inline" 
              id="id-[DRAFT]ЭФБанка&quot;Журналзаявок&quot;-КатегорииЭФ" 
              data-hasbody="false" data-macro-name="anchor"> </span>
        Категории
    </span>
</h1>
'''

print("=== Результат для всех фрагментов ===")
result_all = filter_all_fragments(html)
print(f"'{result_all}'")

print("\n=== Результат для подтвержденных ===")
result_approved = filter_approved_fragments(html)
print(f"'{result_approved}'")