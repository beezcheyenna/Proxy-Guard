async page => {
 const row=ROW;
 const result={lang:row.lang,locale:row.locale,pages:[],errors:[]};
 const error=e=>result.errors.push(String(e));page.on('pageerror',error);
 try {
  await page.context().setExtraHTTPHeaders({'Accept-Language':row.locale+','+row.lang+';q=0.9,en;q=0.5'});
  for(const kind of ['standard','pro']){
   const url='http://10.77.0.1/cgi-bin/luci/admin/services/'+(kind==='standard'?'proxy-guard':'proxy-guard-access');
   await page.goto(url,{waitUntil:'domcontentloaded',timeout:90000});
   if(kind==='standard')await page.getByText(row.standard_label,{exact:true}).first().waitFor({state:'visible',timeout:60000});
   else await page.getByRole('heading',{name:row.pro_heading,exact:true}).waitFor({state:'visible',timeout:60000});
   const dom=await page.evaluate(()=>{
    const roots=Array.from(document.querySelectorAll('.pg-guard'));
    const machine=Array.from(document.querySelectorAll('.pg-guard input,.pg-guard textarea')).filter(e=>/(?:sources[46]|local[46]|exit_url|exit_fallback_url|expected_exit4|endpoint|interfaces|udp_server)$/.test(e.id));
    return {htmlLang:document.documentElement.lang,directions:roots.map(e=>getComputedStyle(e).direction),fields:machine.map(e=>({id:e.id,dir:e.dir})),width:innerWidth,scrollWidth:document.documentElement.scrollWidth,heading:Array.from(document.querySelectorAll('h2')).map(e=>e.textContent),controls:roots.reduce((n,e)=>n+e.querySelectorAll('input,textarea,select,button').length,0)};
   });
   const expected=row.lang==='zh-cn'?'zh':row.lang;
   if(!dom.htmlLang.toLowerCase().startsWith(expected))throw new Error('automatic language did not match: '+JSON.stringify(dom));
   const direction=row.lang==='fa'?'rtl':'ltr';
   if(!dom.directions.length||dom.directions.some(x=>x!==direction))throw new Error('wrong plugin writing direction: '+JSON.stringify(dom));
   if(row.lang==='fa'&&dom.fields.some(x=>x.dir!=='ltr'))throw new Error('machine-value direction regression: '+JSON.stringify(dom));
   const shot='/opt/pg-browser/output/playwright/language-'+row.lang+'-'+kind+'.png';
   await page.screenshot({path:shot,fullPage:true});
   result.pages.push({kind,url,...dom,screenshot:shot,snapshot:await page.locator('body').ariaSnapshot()});
  }
  result.ok=result.errors.length===0;return result;
 } finally {page.off('pageerror',error);}
}
