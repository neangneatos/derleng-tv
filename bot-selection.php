<?php
/** Authenticated per-user channel handoff, shared with the Telegram webhook. */
declare(strict_types=1);
function tv_selection_dir(): string { return dirname(__DIR__).'/.derleng-tv-bot/selections'; }
function tv_selection_state(int $uid, ?array $pick=null): array {
    if($uid<=0)throw new InvalidArgumentException('Invalid identity');
    $dir=tv_selection_dir();if(!is_dir($dir)&&!mkdir($dir,0700,true)&&!is_dir($dir))throw new RuntimeException('State unavailable');
    $lock=fopen($dir.'/'.$uid.'.lock','c');if(!$lock||!flock($lock,LOCK_EX))throw new RuntimeException('State busy');
    try {
        $path=$dir.'/'.$uid.'.json';$s=is_file($path)?json_decode(file_get_contents($path),true):[];
        if(!is_array($s))throw new RuntimeException('Invalid state');
        if($pick!==null) {
            // Telegram IDs are monotonic during normal activity; reset guard after a week idle.
            if(($s['selection']['at']??0)<time()-604800 || $pick['update_id']>($s['selection']['update_id']??-1)) {
                $s['selection']=['cid'=>$pick['cid'],'version'=>(string)$pick['update_id'],'update_id'=>$pick['update_id'],'at'=>time()];
            }
        } else {$s['seen_at']=time();}
        $tmp=$path.'.tmp';if(file_put_contents($tmp,json_encode($s),LOCK_EX)===false)throw new RuntimeException('State write failed');chmod($tmp,0600);if(!rename($tmp,$path))throw new RuntimeException('State replace failed');
        return $s;
    } finally {flock($lock,LOCK_UN);fclose($lock);}
}
function tv_validate_init(string $raw,string $token): array {
    if(strlen($raw)>16384||$raw==='')throw new InvalidArgumentException('Invalid authentication');
    $values=[];
    foreach(explode('&',$raw) as $pair) {
        $parts=explode('=',$pair,2);$key=urldecode($parts[0]);
        if(count($parts)!==2||!preg_match('/^[a-z_]+$/D',$key)||array_key_exists($key,$values))throw new InvalidArgumentException('Invalid authentication');
        $values[$key]=urldecode($parts[1]);
    }
    $hash=$values['hash']??'';unset($values['hash']);
    if(!preg_match('/^[a-f0-9]{64}$/D',$hash))throw new InvalidArgumentException('Invalid authentication');
    ksort($values,SORT_STRING);$lines=[];foreach($values as $k=>$v)$lines[]=$k.'='.$v;
    // Token-based validation includes signature when present; only hash is excluded.
    $key=hash_hmac('sha256',$token,'WebAppData',true);
    if(!hash_equals(hash_hmac('sha256',implode("\n",$lines),$key),$hash))throw new InvalidArgumentException('Invalid authentication');
    $date=$values['auth_date']??'';
    if(!ctype_digit($date)||(int)$date<time()-86400||(int)$date>time()+60)throw new InvalidArgumentException('Expired authentication');
    $user=json_decode($values['user']??'',true);
    if(!is_array($user)||!is_int($user['id']??null)||$user['id']<=0)throw new InvalidArgumentException('Invalid identity');
    return ['uid'=>$user['id'],'auth_date'=>(int)$date];
}
if(defined('DERLENG_SELECTION_LIBRARY_ONLY'))return;
ini_set('display_errors','0');header('Cache-Control: no-store');header('Content-Type: application/json');header('X-Content-Type-Options: nosniff');
function tv_selection_reply(int $code,array $data): void {http_response_code($code);echo json_encode($data);exit;}
if(($_SERVER['REQUEST_METHOD']??'')!=='POST')tv_selection_reply(405,['ok'=>false]);
if((int)($_SERVER['CONTENT_LENGTH']??0)>24576)tv_selection_reply(413,['ok'=>false]);
$raw=file_get_contents('php://input',false,null,0,24577);if(strlen($raw)>24576)tv_selection_reply(413,['ok'=>false]);
$payload=json_decode($raw,true);if(!is_array($payload)||!is_string($payload['init_data']??null))tv_selection_reply(400,['ok'=>false]);
try {
    $config=json_decode(file_get_contents(dirname(__DIR__).'/.derleng-tv-bot/config.json'),true);
    if(!is_string($config['token']??null)||$config['token']==='')throw new RuntimeException('Config unavailable');
    $identity=tv_validate_init($payload['init_data'],$config['token']);
    $state=tv_selection_state($identity['uid']);$selection=$state['selection']??null;
    if($selection!==null&&$selection['at']<time()-900)$selection=null;
    tv_selection_reply(200,['ok'=>true,'auth_date'=>$identity['auth_date'],'selection'=>$selection===null?null:array_intersect_key($selection,array_flip(['cid','version','at']))]);
} catch(InvalidArgumentException $e){tv_selection_reply(401,['ok'=>false,'reauthenticate'=>true]);}
catch(Throwable $e){error_log('DERLENG selection service failure: '.get_class($e));tv_selection_reply(503,['ok'=>false]);}
