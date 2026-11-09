<?php
/** Telegram webhook. Secrets/receipt ledger live outside public_html. */
declare(strict_types=1);
const TV_APP = 'https://tv.derlenghub.com';
function tv_categories(): array { return json_decode(file_get_contents(__DIR__.'/bot-menu.json'), true, 32, JSON_THROW_ON_ERROR); }
function tv_catalog(): array {
    $rows=json_decode(file_get_contents(__DIR__.'/channels_public.json'),true,512,JSON_THROW_ON_ERROR);
    if (!is_array($rows) || !$rows) throw new RuntimeException('Catalog unavailable');
    return array_values(array_filter($rows,fn($c)=>is_array($c) && preg_match('/^[a-zA-Z0-9_-]{8,64}$/D',(string)($c['id']??'')) && is_string($c['n']??null)));
}
function tv_filter(array $rows,string $cat): array {
    return array_values(array_filter($rows,fn($c)=>$cat==='ALL' || ($cat==='Cambodia' && (($c['c']??'')==='KH'||($c['g']??'')==='Cambodia')) || ($c['t']??'')===$cat));
}
function tv_keyboard(array $rows): array {
    $kb=[[['text'=>'🚀 បើកទស្សនា DERLENG TV','web_app'=>['url'=>TV_APP.'/']]]]; $buttons=[];
    foreach(tv_categories() as [$cat,$emoji,$label]) {
        $count=count(tv_filter($rows,$cat));
        if($count) $buttons[]=['text'=>$emoji.' '.$label.' ('.number_format($count).')','callback_data'=>'cat_'.$cat.'_0'];
    }
    $kb=array_merge($kb,array_chunk($buttons,2));
    $kb[]=[['text'=>'🔍 របៀបស្វែងរក','callback_data'=>'nav_search'],['text'=>'📊 ស្ថិតិប៉ុស្តិ៍','callback_data'=>'nav_stats']];
    $kb[]=[['text'=>'❓ ជំនួយ & របៀបមើល','callback_data'=>'nav_help']];
    return ['inline_keyboard'=>$kb];
}
function tv_category_view(array $rows,string $cat,int $page): array {
    $meta=null; foreach(tv_categories() as $c) if($c[0]===$cat) $meta=$c;
    if(!$meta) throw new InvalidArgumentException('Unknown category');
    $rows=tv_filter($rows,$cat);$total=count($rows);$pages=max(1,(int)ceil($total/8));$page=max(0,min($page,$pages-1));$kb=[];
    foreach(array_slice($rows,$page*8,8) as $c) {
        $chars=preg_split('//u',$c['n'],-1,PREG_SPLIT_NO_EMPTY);$name=implode('',array_slice($chars,0,30)).(count($chars)>30?'…':'');
        $kb[]=[['text'=>'▶️ '.$name,'web_app'=>['url'=>TV_APP.'/?cid='.rawurlencode($c['id'])]]];
    }
    $nav=[];if($page>0)$nav[]=['text'=>'◀️ ថយក្រោយ','callback_data'=>'cat_'.$cat.'_'.($page-1)];
    $nav[]=['text'=>'📄 ទំព័រ '.($page+1).'/'.$pages,'callback_data'=>'cat_'.$cat.'_'.$page];
    if($page<$pages-1)$nav[]=['text'=>'បន្ទាប់ ▶️','callback_data'=>'cat_'.$cat.'_'.($page+1)];
    $kb[]=$nav;$kb[]=[['text'=>'🔙 ម៉ឺនុយមេ','callback_data'=>'nav_main'],['text'=>'🚀 បើកកម្មវិធីពេញលេញ','web_app'=>['url'=>TV_APP.'/']]];
    return [$meta[1].' <b>'.$meta[2].' (មាន '.$total.' ប៉ុស្តិ៍)</b>'."\n".'<i>ទំព័រ '.($page+1).' នៃ '.$pages.' • ចុចលើប៉ុស្តិ៍ដើម្បីទស្សនាផ្ទាល់៖</i>', ['inline_keyboard'=>$kb]];
}
function tv_plan(array $u,array $rows): ?array {
    $cb=$u['callback_query']??null;$msg=$cb['message']??($u['message']??null);
    if(!is_array($msg)||($msg['chat']['type']??'')!=='private'||!is_int($msg['chat']['id']??null))return null;
    $chat=$msg['chat']['id'];$mode='main';$cat=null;$page=0;
    if($cb!==null) {
        if(!is_string($cb['data']??null))return null;
        $data=$cb['data'];
        if(preg_match('/^cat_([A-Za-z]+)_([0-9]{1,7})$/D',$data,$m)) {$cat=$m[1];$page=(int)$m[2];$mode='category';}
        elseif(in_array($data,['nav_main','nav_stats','nav_help','nav_search'],true))$mode=substr($data,4);
        else return null;
    } else {
        if(!is_string($msg['text']??null)||trim($msg['text'])==='')return null;
        $cmd=strtolower(explode('@',preg_split('/\s+/',trim($msg['text']))[0])[0]);
        $aliases=['/kh'=>'Cambodia','/kid'=>'Kids','/sport'=>'Sports','/movie'=>'Movies'];
        foreach(tv_categories() as [$key])$aliases['/'.strtolower($key)]=$key;
        if(isset($aliases[$cmd])) {$cat=$aliases[$cmd];$mode='category';}
        elseif(in_array($cmd,['/tv','/play','/player'],true))$mode='tv';
        elseif($cmd==='/stats')$mode='stats'; elseif($cmd==='/help')$mode='help';
    }
    $text='';$markup=tv_keyboard($rows);
    if($mode==='category') {
        try {[$text,$markup]=tv_category_view($rows,$cat,$page);}catch(InvalidArgumentException $e){return null;}
    } elseif($mode==='stats') {
        $text='📊 <b>ប៉ុស្តិ៍ក្នុងបញ្ជី DERLENG TV</b>'."\n\n";
        foreach(tv_categories() as [$key,$emoji,$label])$text.=$emoji.' '.$label.': <b>'.number_format(count(tv_filter($rows,$key))).'</b>'."\n";
    } elseif($mode==='help') {
        $text='❓ <b>DERLENG TV</b>'."\n\n".'ចុច ⛶ Fullscreen ដើម្បីពង្រីកវីដេអូ។ ចុចម្ដងទៀត ឬ Escape/Back ដើម្បីត្រឡប់។'."\n".'ប្រើ Search ដើម្បីស្វែងរកប៉ុស្តិ៍។ បើវីដេអូមិនចាប់ផ្ដើម សូមចុច Play ឬ Reload។'."\n\n".'/start — ម៉ឺនុយមេ'."\n".'/tv — បើកកម្មវិធី';
        foreach(tv_categories() as [$key,$emoji,$label])$text.="\n".'/'.strtolower($key).' — '.$emoji.' '.$label;
        $text.="\n".'/stats — ស្ថិតិប៉ុស្តិ៍';
    } elseif($mode==='search') {
        $text='🔍 <b>ស្វែងរកប៉ុស្តិ៍</b>'."\n\n".'បើក Mini App ហើយប្រើ Search ដើម្បីស្វែងរកឈ្មោះប៉ុស្តិ៍ ប្រភេទ ឬប្រទេស។';
    } elseif($mode==='tv') {
        $text='🚀 <b>សូមចុចខាងក្រោមដើម្បីបើក DERLENG TV៖</b>';
        $markup=['inline_keyboard'=>[[['text'=>'▶️ បើកទស្សនា DERLENG TV','web_app'=>['url'=>TV_APP.'/']]]]];
    } else {
        $text='📺 <b>DERLENG TV</b>'."\n\n".'ប៉ុស្តិ៍ក្នុងបញ្ជី <b>'.number_format(count($rows)).'</b>'."\n".'👇 សូមជ្រើសរើសប្រភេទប៉ុស្តិ៍ ឬបើកកម្មវិធីខាងក្រោម៖';
    }
    $payload=['chat_id'=>$chat,'parse_mode'=>'HTML','reply_markup'=>$markup];
    if($cb!==null && isset($msg['text'],$msg['message_id'])) {
        $method='editMessageText';$payload['message_id']=$msg['message_id'];$payload['text']=$text;$payload['disable_web_page_preview']=true;
    } elseif($mode==='main') {
        $method='sendPhoto';$payload['photo']=TV_APP.'/start_banner.png';$payload['caption']=$text;
    } else {$method='sendMessage';$payload['text']=$text;$payload['disable_web_page_preview']=true;}
    return ['method'=>$method,'payload'=>$payload];
}
function tv_api(string $token,string $method,array $payload): array {
    $ch=curl_init('https://api.telegram.org/bot'.$token.'/'.$method);
    curl_setopt_array($ch,[CURLOPT_POST=>true,CURLOPT_RETURNTRANSFER=>true,CURLOPT_CONNECTTIMEOUT=>5,CURLOPT_TIMEOUT=>($method==='answerCallbackQuery'?4:15),CURLOPT_FOLLOWLOCATION=>false,CURLOPT_PROTOCOLS=>CURLPROTO_HTTPS,CURLOPT_SSL_VERIFYPEER=>true,CURLOPT_SSL_VERIFYHOST=>2,CURLOPT_HTTPHEADER=>['Content-Type: application/json'],CURLOPT_POSTFIELDS=>json_encode($payload,JSON_UNESCAPED_UNICODE)]);
    $body=curl_exec($ch);$code=(int)curl_getinfo($ch,CURLINFO_RESPONSE_CODE);curl_close($ch);
    $r=is_string($body)?json_decode($body,true):null;
    if(!is_array($r))return ['ok'=>false,'error_code'=>0,'uncertain'=>true];
    return $r;
}
function tv_reply(int $status,array $body): void {http_response_code($status);header('Content-Type: application/json');echo json_encode($body);exit;}
if(defined('DERLENG_BOT_LIBRARY_ONLY'))return;
ini_set('display_errors','0');header('Cache-Control: no-store');header('X-Content-Type-Options: nosniff');
if(($_SERVER['REQUEST_METHOD']??'')!=='POST')tv_reply(405,['ok'=>false]);
$configFile=dirname(__DIR__).'/.derleng-tv-bot/config.json';
$config=is_file($configFile)?json_decode(file_get_contents($configFile),true):null;
if(!is_array($config)||!is_string($config['secret']??null)||strlen($config['secret'])<32||!is_string($config['token']??null)||$config['token']==='')tv_reply(503,['ok'=>false]);
if(!hash_equals($config['secret'],$_SERVER['HTTP_X_TELEGRAM_BOT_API_SECRET_TOKEN']??''))tv_reply(403,['ok'=>false]);
if((int)($_SERVER['CONTENT_LENGTH']??0)>262144)tv_reply(413,['ok'=>false]);
$raw=file_get_contents('php://input',false,null,0,262145);
if(strlen($raw)>262144)tv_reply(413,['ok'=>false]);
$u=json_decode($raw,true);
if(!is_array($u)||!is_int($u['update_id']??null)||$u['update_id']<0)tv_reply(400,['ok'=>false]);
$dir=dirname($configFile);$lock=fopen($dir.'/updates.lock','c');
if(!$lock||!flock($lock,LOCK_EX|LOCK_NB))tv_reply(503,['ok'=>false]);
try {
    $file=$dir.'/receipts.json';$state=is_file($file)?json_decode(file_get_contents($file),true):[];
    if(!is_array($state))throw new RuntimeException('Invalid receipt state');
    $id=(string)$u['update_id'];
    if(isset($state[$id])&&in_array($state[$id]['status'],['done','ignored','uncertain','permanent_failure'],true))tv_reply(200,['ok'=>true,'duplicate'=>true]);
    $save=function()use(&$state,$file) {
        // Keep at least 48h of receipts, beyond Telegram's 24h update retention.
        $state=array_filter($state,fn($r)=>($r['at']??0)>=time()-172800);
        $tmp=$file.'.tmp';if(file_put_contents($tmp,json_encode($state),LOCK_EX)===false)throw new RuntimeException('Receipt write failed');chmod($tmp,0600);if(!rename($tmp,$file))throw new RuntimeException('Receipt replace failed');
    };
    // A crash after dispatch begins is ambiguous: never blindly duplicate a send.
    if(($state[$id]['status']??'')==='sending') {
        $state[$id]['status']='uncertain';$save();tv_reply(200,['ok'=>true,'uncertain'=>true]);
    }
    $plan=tv_plan($u,tv_catalog());
    if($plan===null){$state[$id]=['status'=>'ignored','at'=>time()];$save();tv_reply(200,['ok'=>true]);}
    if(isset($u['callback_query']['id']))tv_api($config['token'],'answerCallbackQuery',['callback_query_id'=>$u['callback_query']['id']]);
    $attempt=(int)($state[$id]['attempts']??0)+1;
    if(($state[$id]['retry_at']??0)>time())tv_reply(503,['ok'=>false]);
    $state[$id]=['status'=>'sending','attempts'=>$attempt,'at'=>time()];$save();
    $r=tv_api($config['token'],$plan['method'],$plan['payload']);
    // A definite rejected photo has not been delivered; a text fallback is safe.
    if($plan['method']==='sendPhoto' && !($r['ok']??false) && ($r['error_code']??0)===400) {
        $payload=$plan['payload'];$payload['text']=$payload['caption'];unset($payload['photo'],$payload['caption']);
        $plan=['method'=>'sendMessage','payload'=>$payload];$state[$id]['method']='sendMessage';$save();
        $r=tv_api($config['token'],$plan['method'],$payload);
    }
    $code=(int)($r['error_code']??0);
    $ok=($r['ok']??false)||($plan['method']==='editMessageText' && strpos($r['description']??'','message is not modified')!==false);
    $status=$ok?'done':(($r['uncertain']??false)?'uncertain':(($code===429||$code>=500)?'retry':'permanent_failure'));
    if($status==='retry'&&$attempt>=5)$status='permanent_failure';
    $state[$id]=['status'=>$status,'attempts'=>$attempt,'at'=>time(),'method'=>$plan['method'],'error_code'=>$code,'message_id'=>$r['result']['message_id']??null];
    if($status==='retry')$state[$id]['retry_at']=time()+max(1,(int)($r['parameters']['retry_after']??5));
    $save();
    tv_reply($status==='retry'?503:200,['ok'=>$ok,'status'=>$status]);
} catch(Throwable $e) {error_log('DERLENG webhook internal failure: '.get_class($e));tv_reply(503,['ok'=>false]);}
