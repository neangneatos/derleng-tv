<?php
/** Restricted HTTP HLS bridge. No client-supplied unsigned upstream URLs. */
declare(strict_types=1);
ini_set('display_errors', '0');
header('Cache-Control: no-store');
header('X-Content-Type-Options: nosniff');
function fail(int $status, string $message): void {
    http_response_code($status); header('Content-Type: application/json');
    echo json_encode(['error' => $message]); exit;
}
function b64(string $s): string { return rtrim(strtr(base64_encode($s), '+/', '-_'), '='); }
function public_ip(string $ip): bool {
    if (!filter_var($ip, FILTER_VALIDATE_IP, FILTER_FLAG_IPV4 | FILTER_FLAG_NO_PRIV_RANGE | FILTER_FLAG_NO_RES_RANGE)) return false;
    $n = (int)sprintf('%u', ip2long($ip));
    foreach (['0.0.0.0/8','100.64.0.0/10','192.0.0.0/24','192.0.2.0/24','198.18.0.0/15','198.51.100.0/24','203.0.113.0/24','224.0.0.0/4','240.0.0.0/4'] as $range) {
        [$base,$bits] = explode('/', $range); $mask = (0xffffffff << (32-(int)$bits)) & 0xffffffff;
        if (($n & $mask) === ((int)sprintf('%u',ip2long($base)) & $mask)) return false;
    }
    return true;
}
function checked_url(string $url, array $origin): array {
    if (strlen($url)>4096 || preg_match('/[\x00-\x20\\\\]/', $url)) throw new RuntimeException('Invalid URL');
    $u = parse_url($url);
    if (!$u || !in_array($u['scheme'] ?? '', ['http','https'], true) || isset($u['user']) || isset($u['pass']) || isset($u['fragment'])) throw new RuntimeException('Invalid URL');
    $host = strtolower($u['host'] ?? ''); $port = $u['port'] ?? ($u['scheme']==='https'?443:80);
    // Nested resources and redirects must stay on the catalog channel's exact host.
    if ($host !== strtolower($origin['host']) || !in_array($port, [$origin['port'] ?? ($origin['scheme']==='https'?443:80),80,443], true)) throw new RuntimeException('Origin not allowed');
    if (!preg_match('/^[a-z0-9.-]+$/D', $host)) throw new RuntimeException('Invalid host');
    $ips = filter_var($host, FILTER_VALIDATE_IP) ? [$host] : (gethostbynamel($host) ?: []);
    if (!$ips) throw new RuntimeException('DNS unavailable');
    foreach ($ips as $ip) if (!public_ip($ip)) throw new RuntimeException('Private destination');
    return [$host,$port,$ips[0]];
}
function absolute_url(string $ref, string $base): string {
    if (preg_match('~^[a-zA-Z][a-zA-Z0-9+.-]*:~', $ref)) return $ref;
    $u=parse_url($base); $origin=$u['scheme'].'://'.$u['host'].(isset($u['port'])?':'.$u['port']:'');
    if (substr($ref,0,2)==='//') return $u['scheme'].':'.$ref;
    if (substr($ref,0,1)==='?') return $origin.($u['path'] ?? '/').$ref;
    $path=substr($ref,0,1)==='/'?$ref:substr($u['path']??'/',0,strrpos($u['path']??'/','/')+1).$ref;
    [$part,$query]=array_pad(explode('?', $path,2),2,null); $parts=[];
    foreach(explode('/',$part) as $p) { if($p==='..') array_pop($parts); elseif($p!=='.' && $p!=='') $parts[]=$p; }
    return $origin.'/'.implode('/',$parts).($query!==null?'?'.$query:'');
}
function secret(): string {
    // Outside the document root; never present in the deployment archive or Git.
    $path=dirname(__DIR__).'/.derleng-tv-relay-key';
    $f=fopen($path,'c+b'); if(!$f || !flock($f,LOCK_EX)) throw new RuntimeException('Key unavailable');
    chmod($path,0600); $key=stream_get_contents($f);
    if(strlen($key)!==32) { $key=random_bytes(32); ftruncate($f,0); rewind($f); fwrite($f,$key); fflush($f); }
    flock($f,LOCK_UN); fclose($f); return $key;
}
function signed_url(string $url,string $cid,string $key,array $origin): string {
    checked_url($url,$origin);
    $data=b64(json_encode(['c'=>$cid,'u'=>$url],JSON_UNESCAPED_SLASHES));
    return '/relay.php?t='.$data.'.'.b64(hash_hmac('sha256',$data,$key,true));
}
function fetch_resource(string $url,array $origin): array {
    $range=$_SERVER['HTTP_RANGE']??'';
    if($range!=='' && !preg_match('/^bytes=\d+-\d*$/D',$range)) fail(416,'Unsupported range');
    for($redirect=0;$redirect<4;$redirect++) {
        [$host,$port,$ip]=checked_url($url,$origin); $body='';$headers=[]; $tooLarge=false;
        $ch=curl_init($url);
        curl_setopt_array($ch,[CURLOPT_FOLLOWLOCATION=>false,CURLOPT_CONNECTTIMEOUT=>5,CURLOPT_TIMEOUT=>18,
            CURLOPT_PROTOCOLS=>CURLPROTO_HTTP|CURLPROTO_HTTPS,CURLOPT_PROXY=>'',CURLOPT_SSL_VERIFYPEER=>true,CURLOPT_SSL_VERIFYHOST=>2,
            CURLOPT_RESOLVE=>[$host.':'.$port.':'.$ip],CURLOPT_USERAGENT=>'DERLENG-TV/1.0',
            CURLOPT_HTTPHEADER=>$range!==''?['Range: '.$range]:[],
            CURLOPT_HEADERFUNCTION=>function($ch,$line)use(&$headers){$n=strlen($line);if(strpos($line,':')!==false){[$k,$v]=explode(':',$line,2);$headers[strtolower(trim($k))]=trim($v);}return $n;},
            CURLOPT_WRITEFUNCTION=>function($ch,$chunk)use(&$body,&$tooLarge){if(strlen($body)+strlen($chunk)>16777216){$tooLarge=true;return 0;}$body.=$chunk;return strlen($chunk);}]);
        $ok=curl_exec($ch);$status=(int)curl_getinfo($ch,CURLINFO_RESPONSE_CODE);curl_close($ch);
        if($tooLarge) throw new RuntimeException('Resource too large');
        if($ok===false) throw new RuntimeException('Upstream unavailable');
        if(in_array($status,[301,302,303,307,308],true) && isset($headers['location'])) {$url=absolute_url($headers['location'],$url);continue;}
        if(!in_array($status,[200,206],true)) throw new RuntimeException('Upstream response failed');
        return [$body,$headers,$status,$url];
    }
    throw new RuntimeException('Too many redirects');
}
if (($_SERVER['REQUEST_METHOD']??'GET')!=='GET') fail(405,'GET only');
if (isset($_GET['status'])) { header('Content-Type: application/json'); echo json_encode(['php'=>true,'curl'=>extension_loaded('curl')]); exit; }
if (!extension_loaded('curl')) fail(503,'Relay runtime unavailable');
try {
    $key=secret(); $url=null; $cid=$_GET['cid']??'';
    if(isset($_GET['t'])) {
        if(!is_string($_GET['t']) || strlen($_GET['t'])>8000) fail(400,'Invalid token');
        $pieces=explode('.',$_GET['t']);if(count($pieces)!==2 || !hash_equals(b64(hash_hmac('sha256',$pieces[0],$key,true)),$pieces[1])) fail(403,'Invalid signature');
        $data=json_decode(base64_decode(strtr($pieces[0],'-_','+/'),true)?:'',true);
        if(!is_array($data)) fail(403,'Invalid token');
        $cid=$data['c']??''; $url=$data['u']??null;
    }
    if(!is_string($cid) || !preg_match('/^[a-f0-9]{16}$/D',$cid)) fail(400,'Catalog channel required');
    $catalog=json_decode(file_get_contents(__DIR__.'/channels_public.json'),true);$source=null;
    foreach($catalog as $c) if($c['id']===$cid){$source=$c['u'];break;}
    if(!$source || strpos($source,'http://')!==0) fail(404,'HTTP channel not found');
    $origin=parse_url($source);$url=$url??$source;if(!is_string($url)) fail(400,'Invalid resource');
    $slot=null;
    for($i=0;$i<6;$i++) { $f=fopen(dirname(__DIR__).'/.derleng-tv-relay-slot-'.$i,'c'); if($f && flock($f,LOCK_EX|LOCK_NB)){$slot=$f;break;} if($f) fclose($f); }
    if(!$slot) {header('Retry-After: 2');fail(503,'Relay busy');}
    [$body,$headers,$status,$final]=fetch_resource($url,$origin);
    if(strncmp(ltrim($body), '#EXTM3U',7)===0) {
        if(strlen($body)>1048576) throw new RuntimeException('Playlist too large');
        $lines=explode("\n",str_replace("\r",'', $body));
        foreach($lines as &$line) {
            $trim=trim($line);if($trim==='') continue;
            if($trim[0]!=='#') $line=signed_url(absolute_url($trim,$final),$cid,$key,$origin);
            else $line=preg_replace_callback('/\bURI="([^"]+)"/',function($m)use($final,$cid,$key,$origin){return 'URI="'.signed_url(absolute_url($m[1],$final),$cid,$key,$origin).'"';},$line);
        } unset($line);
        header('Content-Type: application/vnd.apple.mpegurl');echo implode("\n",$lines);
    } else {
        $type=strtolower(explode(';',$headers['content-type']??'application/octet-stream')[0]);
        if(in_array($type,['text/html','application/xhtml+xml','image/svg+xml'],true)) throw new RuntimeException('Not a media resource');
        http_response_code($status);header('Content-Type: application/octet-stream');
        if(isset($headers['content-range']) && preg_match('/^bytes [0-9]+-[0-9]+\/[0-9*]+$/D',$headers['content-range'])) header('Content-Range: '.$headers['content-range']);
        header('Accept-Ranges: bytes');header('Content-Length: '.strlen($body));echo $body;
    }
    flock($slot,LOCK_UN);fclose($slot);
} catch(Throwable $e) { fail(502,'Stream relay unavailable'); }
