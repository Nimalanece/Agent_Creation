from app.services.selenium_service import _build_selenium_code_from_analysis
analysis={
    'url':'https://opensource-demo.orangehrmlive.com/web/index.php/auth/login',
    'title':'OrangeHRM',
    'links':[{'href':'http://www.orangehrm.com','text':'OrangeHRM','tag':'a','selector':'a'}],
    'inputs':[{'id':'txtUsername','name':'username','type':'text','placeholder':'Username','tag':'input'},{'id':'txtPassword','name':'password','type':'password','placeholder':'Password','tag':'input'}],
    'buttons':[{'id':'btnLogin','type':'submit','text':'Login','tag':'button'}],
    'forms':[{'id':'frmLogin','name':'loginForm','inputs':[{'id':'txtUsername','name':'username','type':'text','placeholder':'Username','tag':'input'},{'id':'txtPassword','name':'password','type':'password','placeholder':'Password','tag':'input'}],'buttons':[{'id':'btnLogin','type':'submit','text':'Login','tag':'button'}]}]
}
code = _build_selenium_code_from_analysis([],analysis=analysis,scenarios={'scenarios':[{'title':'Login to OrangeHRM','mapping':{'page':'auth'}}]})
print(code)
