#!/usr/bin/env python3
"""Replace SETTINGS_HTML in web_active_link.py with sidebar version"""
with open('web_active_link.py', 'r') as f:
    content = f.read()

marker = 'SETTINGS_HTML = """'
start = content.find(marker)
first = content.find('"""', start + len(marker))
second = content.find('"""', first + 3)
end = content.find('"""', second + 3)

# Read the new HTML from a separate file to avoid escaping issues
new_html = '''SETTINGS_HTML = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>LINK 设置</title>
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;background:#f0f2f5;color:#333;display:flex;min-height:100vh}
.sidebar{width:180px;background:#fff;border-right:1px solid #e0e0e0;padding:20px 0;flex-shrink:0;display:flex;flex-direction:column}
.sidebar h1{font-size:16px;padding:0 20px 16px;color:#1a1a2e;border-bottom:1px solid #eee}
.sidebar .tab{padding:12px 20px;cursor:pointer;font-size:14px;color:#555;display:flex;align-items:center;gap:8px;border-left:3px solid transparent;transition:all .15s}
.sidebar .tab:hover{background:#f5f5f5;color:#1a73e8}
.sidebar .tab.active{background:#e8f0fe;color:#1a73e8;border-left-color:#1a73e8;font-weight:500}
.main{flex:1;padding:24px 32px;max-width:800px;overflow-y:auto}
.main h2{font-size:18px;margin-bottom:16px;color:#1a1a2e}
.card{background:#fff;border-radius:12px;padding:20px;margin-bottom:16px;box-shadow:0 1px 4px rgba(0,0,0,.08)}
.card h3{font-size:14px;margin-bottom:10px;color:#1a73e8}
.field{margin-bottom:14px}
.field label{display:block;font-size:13px;color:#555;margin-bottom:4px;font-weight:500}
.field input,.field select{width:100%;padding:10px 12px;border:1px solid #ddd;border-radius:8px;font-size:14px;outline:none;transition:border-color .2s}
.field input:focus,.field select:focus{border-color:#1a73e8}
.radio-group{display:flex;gap:24px;margin-bottom:4px}
.radio-group label{font-size:14px;cursor:pointer;display:flex;align-items:center;gap:4px;color:#333;padding:8px 12px;border:2px solid #e0e0e0;border-radius:8px;transition:all .2s}
.radio-group label:has(input:checked){border-color:#1a73e8;background:#e8f0fe}
.btn{padding:10px 20px;border:none;border-radius:8px;cursor:pointer;font-size:13px;font-weight:500;transition:all .2s}
.btn-primary{background:#1a73e8;color:#fff}
.btn-primary:hover{background:#1557b0}
.btn-primary:disabled{background:#ccc;cursor:not-allowed}
.btn-secondary{background:#e8eaed;color:#333}
.btn-secondary:hover{background:#d2d5d9}
.btn-danger{background:#fff;color:#d93025;border:1px solid #ddd}
.btn-danger:hover{background:#fce8e8;border-color:#d93025}
.status{display:none;padding:12px 16px;border-radius:8px;margin-bottom:16px;font-size:14px}
.status.success{display:block;background:#e8f5e9;color:#2e7d32;border:1px solid #c8e6c9}
.status.error{display:block;background:#fce8e8;color:#d93025;border:1px solid #f5c6cb}
.hidden{display:none!important}
.tab-content{display:none}
.tab-content.active{display:block}
.model-info{font-size:12px;color:#888;margin-top:6px}
#auth-list{max-height:400px;overflow-y:auto}
.back-link{display:block;padding:16px 20px 0;font-size:12px;color:#888;text-decoration:none;margin-top:auto}
.back-link:hover{color:#1a73e8}
.footer-actions{display:flex;gap:10px;margin-top:8px;padding-top:16px;border-top:1px solid #eee}
</style>
</head>
<body>
<div class="sidebar">
  <h1>⚙ LINK</h1>
  <div class="tab active" onclick="switchTab('model')">\U0001F916 模型</div>
  <div class="tab" onclick="switchTab('auth')">\U0001F510 授权</div>
  <div class="tab" onclick="switchTab('about')">ℹ 关于</div>
  <a href="/" class="back-link">← 返回聊天</a>
</div>
<div class="main">
  <div id="status" class="status"></div>
  <div id="tab-model" class="tab-content active">
    <h2>\U0001F916 模型配置</h2>
    <div class="card"><h3>运行模式</h3><div class="radio-group"><label><input type="radio" name="mode" value="online" checked onchange="toggleMode()"> \U0001F310 在线（API）</label><label><input type="radio" name="mode" value="offline" onchange="toggleMode()"> \U0001F4BB 本地</label></div></div>
    <div id="online-settings" class="card"><h3>在线 API</h3><div class="field"><label>服务商</label><select id="provider" onchange="updateBaseUrl()"><option value="deepseek">DeepSeek</option><option value="openai">OpenAI</option><option value="custom">自定义</option></select></div><div class="field"><label>API 地址</label><input id="api-base" placeholder="https://api.deepseek.com"></div><div class="field"><label>API Key</label><input id="api-key" type="password" placeholder="sk-..."></div><div class="field"><label>模型</label><input id="model-name" placeholder="deepseek-chat"></div><div class="field"><label>Temperature</label><input id="temperature" type="number" step="0.1" min="0" max="2" value="0.7"></div></div>
    <div id="offline-settings" class="card hidden"><h3>本地模型</h3><div class="field"><label>选择模型</label><select id="offline-model"></select></div><div class="model-info" id="model-info"></div></div>
    <div class="footer-actions"><button class="btn btn-primary" onclick="saveSettings()">保存设置</button><button class="btn btn-secondary" onclick="testConnection()">测试连接</button></div>
  </div>
  <div id="tab-auth" class="tab-content">
    <h2>\U0001F510 外部文件授权</h2>
    <div class="card"><h3>添加授权</h3><div style="display:flex;gap:8px;flex-wrap:wrap"><input id="auth-path" placeholder="/path/to/dir" style="flex:1;min-width:180px;padding:10px 12px;border:1px solid #ddd;border-radius:8px;font-size:13px"><select id="auth-mode" style="padding:10px;border:1px solid #ddd;border-radius:8px;font-size:13px"><option value="read">只读</option><option value="read_write">读写</option></select><select id="auth-type" style="padding:10px;border:1px solid #ddd;border-radius:8px;font-size:13px"><option value="temporary">临时</option><option value="permanent">永久</option></select><button class="btn btn-secondary" onclick="addAuthorization()" style="padding:10px 16px">添加</button></div><div style="font-size:12px;color:#888;margin-top:6px">授权目录后，其下所有文件自动获得读写权限</div></div>
    <div class="card"><h3>已授权路径</h3><div id="auth-list" style="font-size:13px"><div style="color:#999;padding:8px 0">加载中...</div></div></div>
  </div>
  <div id="tab-about" class="tab-content">
    <h2>ℹ 关于 LINK</h2>
    <div class="card"><div style="font-size:14px;line-height:2"><div><strong>版本:</strong> 3.0</div><div><strong>架构:</strong> 模块化 | FastAPI + WebSocket</div><div><strong>记忆引擎:</strong> <span id="about-memory">加载中...</span></div><div><strong>大脑引擎:</strong> <span id="about-brain">加载中...</span></div><div><strong>运行状态:</strong> <span id="about-status">加载中...</span></div></div></div>
  </div>
</div>
<script>
function switchTab(n){document.querySelectorAll('.tab').forEach(function(t){t.classList.remove('active');});document.querySelectorAll('.tab-content').forEach(function(c){c.classList.remove('active');});var t=document.querySelector('.tab[onclick*="'+n+'"]');if(t)t.classList.add('active');document.getElementById('tab-'+n).classList.add('active');}
function showStatus(m,t){var e=document.getElementById('status');e.textContent=m;e.className='status '+t;setTimeout(function(){e.className='status';},4000);}
function toggleMode(){var o=document.querySelector('input[name=mode]:checked').value==='online';document.getElementById('online-settings').classList.toggle('hidden',!o);document.getElementById('offline-settings').classList.toggle('hidden',o);}
function updateBaseUrl(){var v=document.getElementById('provider').value;var u={deepseek:'https://api.deepseek.com',openai:'https://api.openai.com/v1',custom:''};document.getElementById('api-base').value=u[v]||'';}
async function loadModels(){var s=document.getElementById('offline-model');s.innerHTML='<option>加载中...</option>';try{var r=await fetch('/api/models');var d=await r.json();if(d.models&&d.models.length>0){s.innerHTML=d.models.map(function(m){var n=['bge-m3','nomic-embed-text','all-MiniLM'].some(function(e){return m.indexOf(e)===0;})?' (仅嵌入)':'';return '<option value="'+m+'">'+m+n+'</option>';}).join('');}else{s.innerHTML='<option>无可用模型</option>';}}catch(e){s.innerHTML='<option>加载失败</option>';}}
async function loadSettings(){try{var r=await fetch('/api/settings');var s=await r.json();var q=document.querySelector('input[name=mode][value="'+s.mode+'"]');if(q)q.checked=true;if(s.provider)document.getElementById('provider').value=s.provider;if(s.api_base)document.getElementById('api-base').value=s.api_base;if(s.api_key_display)document.getElementById('api-key').placeholder=s.api_key_display;if(s.model)document.getElementById('model-name').value=s.model;if(s.temperature)document.getElementById('temperature').value=s.temperature;if(s.offline_model){var sel=document.getElementById('offline-model');for(var i=0;i<sel.options.length;i++){if(sel.options[i].value===s.offline_model){sel.value=s.offline_model;break;}}}toggleMode();}catch(e){showStatus('加载失败: '+e,'error');}}
async function saveSettings(){var d={mode:document.querySelector('input[name=mode]:checked').value,provider:document.getElementById('provider').value,api_base:document.getElementById('api-base').value,api_key:document.getElementById('api-key').value,model:document.getElementById('model-name').value,temperature:parseFloat(document.getElementById('temperature').value)||0.7,offline_model:document.getElementById('offline-model').value,};try{var r=await fetch('/api/settings',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(d)});var s=await r.json();showStatus(s.message||'已保存','success');}catch(e){showStatus('保存失败: '+e,'error');}}
async function testConnection(){var d={provider:document.getElementById('provider').value,api_base:document.getElementById('api-base').value,api_key:document.getElementById('api-key').value,model:document.getElementById('model-name').value,};try{var r=await fetch('/api/settings/test',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(d)});var s=await r.json();showStatus(s.message||s.error||'完成',s.success?'success':'error');}catch(e){showStatus('测试失败: '+e,'error');}}
async function loadAuthorizations(){var e=document.getElementById('auth-list');if(!e)return;try{var r=await fetch('/api/permissions');var d=await r.json();var p=d.permissions||[];if(p.length===0){e.innerHTML='<div style="color:#999;padding:8px 0">暂无外部授权</div>';return;}var h='';for(var i=0;i<p.length;i++){var x=p[i];var ic=x.under_project?'\U0001F4C1':'\U0001F513';var ml=x.mode==='read_write'?'读写':x.mode==='read'?'只读':'写入';var tl=x.type==='permanent'?'永久':'临时';var db=x.under_project?'':'<button class="btn btn-danger" style="padding:3px 10px;font-size:11px" data-path="'+encodeURIComponent(x.path)+'" onclick="removeAuthorization(decodeURIComponent(this.dataset.path))">删除</button>';h+='<div style="display:flex;align-items:center;gap:8px;padding:8px 0;border-bottom:1px solid #f0f0f0;word-break:break-all"><span>'+ic+'</span><span style="flex:1;font-size:13px">'+x.path+'</span><span style="font-size:11px;color:#888;white-space:nowrap">['+ml+' / '+tl+']</span>'+db+'</div>';}e.innerHTML=h;}catch(e){e.innerHTML='<div style="color:#d93025;padding:8px 0">加载失败</div>';}}
async function addAuthorization(){var p=document.getElementById('auth-path').value.trim();if(!p){showStatus('请输入路径','error');return;}var m=document.getElementById('auth-mode').value;var t=document.getElementById('auth-type').value;try{var r=await fetch('/api/permissions',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({path:p,mode:m,type:t})});var d=await r.json();if(d.success){showStatus('授权成功','success');document.getElementById('auth-path').value='';loadAuthorizations();}else{showStatus('授权失败: '+(d.message||'未知错误'),'error');}}catch(e){showStatus('请求失败: '+e,'error');}}
async function removeAuthorization(p){if(!confirm('确定撤销授权?\\n'+p))return;try{var r=await fetch('/api/permissions/remove',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({path:p})});var d=await r.json();showStatus(d.success?'已撤销授权':'撤销失败',d.success?'success':'error');loadAuthorizations();}catch(e){showStatus('请求失败: '+e,'error');}}
async function loadAboutInfo(){try{var r=await fetch('/api/debug');var d=await r.json();var m=d.memory||{};var b=d.brain||{};document.getElementById('about-memory').textContent=(m.available?'✅ ':'❌ ')+(m.stats?.total_memories||0)+' 条记忆';document.getElementById('about-brain').textContent=(b.available?'✅ ':'❌ ')+(b.config?.model_name||'N/A');document.getElementById('about-status').textContent=(b.health?.overall_status||'unknown')+' | 运行 '+(d.web?.uptime?Math.floor(d.web.uptime)+'s':'?');}catch(e){}}
loadSettings();loadModels();loadAuthorizations();loadAboutInfo();
</script>
</body>
</html>"""

content = content[:start] + new_html + content[end+3:]

with open('web_active_link.py', 'w') as f:
    f.write(content)
print("Done! Written", len(content), "bytes")
