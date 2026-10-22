const express=require('express');
const netApi=require('net-browserify');
const fs=require('node:fs');
const path=require('node:path');
const root=path.dirname(require.resolve('prismarine-web-client/package.json'));
const app=express();
app.disable('x-powered-by');
app.get('/config.json',(_request,response)=>response.json({defaultHost:'127.0.0.1',defaultHostPort:55917,defaultProxy:'',defaultProxyPort:0,defaultVersion:'1.16.5'}));
app.use(netApi({to:[{host:'127.0.0.1',port:55917}],timeout:240000}));
app.get('/',(_request,response)=>{
 let html=fs.readFileSync(path.join(root,'public','index.html'),'utf8');
 html=html.replace('<title>Prismarine Web Client</title>','<title>Mondcraft - Ghost</title>');
 html=html.replace('</head>','<script>localStorage.setItem("server","127.0.0.1");localStorage.setItem("serverport","55916");localStorage.setItem("proxy","");localStorage.setItem("proxyport","");localStorage.setItem("username","Ghost");localStorage.setItem("version","1.16.5");</script></head>');
 html=html.replace('</body>','<script src="/mondcraft-entry.js?v=native1"></script></body>');
 response.set('Cache-Control','no-store').type('html').send(html);
});
app.get('/mondcraft-entry.js',(_request,response)=>response.type('application/javascript').sendFile(path.join(__dirname,'client-entry.js')));
app.use(express.static(path.join(root,'public')));
app.listen(6061,'127.0.0.1',()=>console.log('MONDCRAFT_PLAYABLE_CLIENT http://127.0.0.1:6061'));