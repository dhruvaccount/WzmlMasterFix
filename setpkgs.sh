#!/bin/bash

ARIA2C=$1
SERVICE_CORES=${2:-}
CPU_LIMIT=${3:-20}
SABNZBDPLUS=$4

if [ -n "$SERVICE_CORES" ]; then
    ARIA2_CMD="taskset -c $SERVICE_CORES $ARIA2C"
    SAB_CMD="taskset -c $SERVICE_CORES cpulimit -l $CPU_LIMIT -- $SABNZBDPLUS"
else
    ARIA2_CMD="$ARIA2C"
    SAB_CMD="cpulimit -l $CPU_LIMIT -- $SABNZBDPLUS"
fi

tracker_list=$(curl -Ns https://ngosang.github.io/trackerslist/trackers_all_http.txt | awk '$0' | tr '\n\n' ',')
$ARIA2_CMD --allow-overwrite=true --auto-file-renaming=true --bt-enable-lpd=true --bt-detach-seed-only=true \
       --bt-remove-unselected-file=true --bt-tracker="[$tracker_list]" --bt-max-peers=0 --enable-rpc=true \
       --rpc-listen-all=true --rpc-listen-port=6800 --rpc-max-request-size=1024M \
       --max-connection-per-server=16 --max-concurrent-downloads=1000 --split=16 --min-split-size=32M \
       --seed-ratio=0 --check-integrity=true --continue=true --daemon=true --disk-cache=64M --force-save=true \
       --follow-torrent=mem --check-certificate=false --optimize-concurrent-downloads=true \
       --http-accept-gzip=true --max-file-not-found=0 --max-tries=20 --peer-id-prefix=-qB4520- --reuse-uri=true \
       --content-disposition-default-utf8=true --user-agent=Wget/1.12 --peer-agent=qBittorrent/4.5.2 --quiet=true \
       --summary-interval=0 --max-upload-limit=1K \
       --save-session=aria2.session --save-session-interval=30 \
       --bt-max-open-files=1000 --bt-request-peer-speed-limit=1M \
       --enable-dht=true --enable-peer-exchange=true \
       --listen-port=6881-6999 --dht-listen-port=6881-6999 --file-allocation=falloc
if [ -n "$SABNZBDPLUS" ]; then
    $SAB_CMD -f configs/sabnzbd/SABnzbd.ini -s :::8070 -b 0 -d -c -l 0 --console
fi
