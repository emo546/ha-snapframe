#!/usr/bin/with-contenv bashio

SMB_SERVER=$(bashio::config 'smb_server')
SMB_SHARE=$(bashio::config 'smb_share')
SMB_VERSION=$(bashio::config 'smb_version')
SMB_USERNAME=$(bashio::config 'smb_username')
SMB_PASSWORD=$(bashio::config 'smb_password')
WATCH_FOLDER=$(bashio::config 'watch_folder')
OUTPUT_FOLDER=$(bashio::config 'output_folder')
DELETE_ORIGINAL=$(bashio::config 'delete_original')
JPG_QUALITY=$(bashio::config 'jpg_quality')
THUMB_QUALITY=$(bashio::config 'thumb_quality')
THUMB_MAX_PX=$(bashio::config 'thumb_max_px')
THUMB_CACHE=$(bashio::config 'thumb_cache')
SCAN_INTERVAL_HOURS=$(bashio::config 'scan_interval_hours')
SLIDESHOW_SECONDS=$(bashio::config 'slideshow_seconds')
WEB_PORT=$(bashio::config 'web_port')
BASIC_AUTH_USER=$(bashio::config 'basic_auth_user')
BASIC_AUTH_PASSWORD=$(bashio::config 'basic_auth_password')
LANGUAGE=$(bashio::config 'language')
SLEEP_START=$(bashio::config 'sleep_start')
SLEEP_END=$(bashio::config 'sleep_end')
WEATHER_PHOTO_INTERVAL=$(bashio::config 'weather_photo_interval')
WEATHER_MODE_DURATION_MIN=$(bashio::config 'weather_mode_duration_minutes')
ANTHROPIC_API_KEY=$(bashio::config 'anthropic_api_key')
API_TOKEN=$(bashio::config 'api_token')
MQTT_ENABLED=$(bashio::config 'mqtt_enabled')
MQTT_HOST=$(bashio::config 'mqtt_host')
MQTT_PORT=$(bashio::config 'mqtt_port')
MQTT_USER=$(bashio::config 'mqtt_username')
MQTT_PASSWORD=$(bashio::config 'mqtt_password')

# bashio vracia "null" pre nové polia ktoré ešte nie sú v options – nahraď defaultmi
[ "${THUMB_QUALITY}" = "null" ]      && THUMB_QUALITY="82"
[ "${THUMB_MAX_PX}" = "null" ]       && THUMB_MAX_PX="1024"
[ "${THUMB_CACHE}" = "null" ]       && THUMB_CACHE="addon"
[ "${SMB_VERSION}" = "null" ]       && SMB_VERSION="3.0"
[ "${BASIC_AUTH_USER}" = "null" ]    && BASIC_AUTH_USER=""
[ "${BASIC_AUTH_PASSWORD}" = "null" ] && BASIC_AUTH_PASSWORD=""
[ "${LANGUAGE}" = "null" ]            && LANGUAGE="sk"
[ "${SLEEP_START}" = "null" ]         && SLEEP_START=""
[ "${SLEEP_END}" = "null" ]           && SLEEP_END=""
[ "${WEATHER_PHOTO_INTERVAL}" = "null" ]    && WEATHER_PHOTO_INTERVAL="8"
[ "${WEATHER_MODE_DURATION_MIN}" = "null" ] && WEATHER_MODE_DURATION_MIN="120"
[ "${ANTHROPIC_API_KEY}" = "null" ]           && ANTHROPIC_API_KEY=""
[ "${API_TOKEN}" = "null" ]                   && API_TOKEN=""
[ "${MQTT_ENABLED}" = "null" ]                && MQTT_ENABLED="true"
[ "${MQTT_HOST}" = "null" ]                   && MQTT_HOST=""
[ "${MQTT_PORT}" = "null" ]                   && MQTT_PORT="1883"
[ "${MQTT_USER}" = "null" ]                   && MQTT_USER=""
[ "${MQTT_PASSWORD}" = "null" ]               && MQTT_PASSWORD=""

# Broker si vypýtame od Supervisora (služba mqtt), pokiaľ ho používateľ
# nezadal ručne. Bez brokera sa MQTT ticho preskočí – nie je povinné.
if [ "${MQTT_ENABLED}" = "true" ] && [ -z "${MQTT_HOST}" ]; then
    if bashio::services.available "mqtt"; then
        MQTT_HOST=$(bashio::services mqtt "host")
        MQTT_PORT=$(bashio::services mqtt "port")
        MQTT_USER=$(bashio::services mqtt "username")
        MQTT_PASSWORD=$(bashio::services mqtt "password")
        bashio::log.info "MQTT broker zo Supervisora: ${MQTT_HOST}:${MQTT_PORT}"
    fi
fi
if [ "${MQTT_ENABLED}" != "true" ]; then
    MQTT_HOST=""
fi

bashio::log.info "SMB server: ${SMB_SERVER}"
bashio::log.info "SMB share: ${SMB_SHARE}"
bashio::log.info "Watch folder: ${WATCH_FOLDER}"
bashio::log.info "Output folder: ${OUTPUT_FOLDER}"
bashio::log.info "Delete original: ${DELETE_ORIGINAL}"
bashio::log.info "Scan interval (hours): ${SCAN_INTERVAL_HOURS}"
bashio::log.info "Thumbnail: max ${THUMB_MAX_PX}px, kvalita ${THUMB_QUALITY}, cache: ${THUMB_CACHE}"

if [ -z "${SMB_USERNAME}" ] || [ -z "${SMB_PASSWORD}" ]; then
    bashio::log.error "smb_username alebo smb_password nie je nastavené v konfigurácii. Add-on sa zastavuje."
    exit 1
fi

mkdir -p /sambamount

# Heslo sa nikdy nedrží v súbore dlhšie než samotný mount – credentials súbor
# vznikne pri každom pokuse nanovo a hneď sa aj prepíše.
mount_share() {
    local cred rc
    cred=$(mktemp)
    chmod 600 "${cred}"
    {
        echo "username=${SMB_USERNAME}"
        echo "password=${SMB_PASSWORD}"
    } > "${cred}"
    mount -t cifs "//${SMB_SERVER}/${SMB_SHARE}" /sambamount \
        -o "credentials=${cred},vers=${SMB_VERSION},iocharset=utf8,file_mode=0660,dir_mode=0770,uid=0,gid=0"
    rc=$?
    shred -u "${cred}" 2>/dev/null || rm -f "${cred}"
    return ${rc}
}

# Samotné "je to primountované" nestačí: keď NAS medzitým zmizne, mount v
# tabuľke zostane, ale každé čítanie skončí chybou.
share_healthy() {
    grep -q " /sambamount " /proc/mounts 2>/dev/null && ls /sambamount > /dev/null 2>&1
}

bashio::log.info "Pripájam CIFS share //${SMB_SERVER}/${SMB_SHARE} na /sambamount (SMB ${SMB_VERSION})..."
if ! mount_share; then
    bashio::log.error "Pripojenie CIFS zlyhalo! Skontroluj smb_server, smb_username, smb_password a smb_version v konfigurácii."
    sleep 30
    exit 1
fi

bashio::log.info "CIFS pripojené úspešne."

# Bez tohto add-on po výpadku NAS beží ďalej naslepo: web server odpovedá,
# ale knižnica fotiek je prázdna, kým add-on niekto ručne nereštartuje.
(
    while true; do
        sleep 60
        if ! share_healthy; then
            bashio::log.warning "CIFS share nie je dostupný – skúšam premountovať"
            umount -l /sambamount > /dev/null 2>&1
            if mount_share; then
                bashio::log.info "CIFS share znova pripojený"
            else
                bashio::log.error "Premountovanie zlyhalo, skúsim o minútu znova"
            fi
        fi
    done
) &
MOUNT_WATCHDOG_PID=$!
trap 'kill "${MOUNT_WATCHDOG_PID}" 2> /dev/null' EXIT

mkdir -p "${WATCH_FOLDER}"
mkdir -p "${OUTPUT_FOLDER}"
mkdir -p /data

export WATCH_FOLDER
export OUTPUT_FOLDER
export DELETE_ORIGINAL
export JPG_QUALITY
export THUMB_QUALITY
export THUMB_MAX_PX
export THUMB_CACHE
export SCAN_INTERVAL_SECONDS=$((SCAN_INTERVAL_HOURS * 3600))
export SLIDESHOW_SECONDS
export WEB_PORT
export BASIC_AUTH_USER
export BASIC_AUTH_PASSWORD
export LANGUAGE
export SLEEP_START
export SLEEP_END
export WEATHER_PHOTO_INTERVAL
export WEATHER_MODE_DURATION_MIN
export ANTHROPIC_API_KEY
export API_TOKEN
export MQTT_HOST
export MQTT_PORT
export MQTT_USER
export MQTT_PASSWORD
SNAPFRAME_VERSION=$(bashio::addon.version 2>/dev/null || echo "")
export SNAPFRAME_VERSION
export PYTHONPATH="/usr/bin:${PYTHONPATH:-}"

bashio::log.info "Slideshow interval: ${SLIDESHOW_SECONDS} s"
bashio::log.info "Web port: ${WEB_PORT}"
if [ -n "${BASIC_AUTH_USER}" ]; then
    bashio::log.info "HTTP Basic Auth zapnutá pre: ${BASIC_AUTH_USER}"
fi
if [ -n "${MQTT_HOST}" ]; then
    bashio::log.info "MQTT discovery zapnuté – senzory sa v HA objavia samé"
fi
if [ -n "${API_TOKEN}" ]; then
    bashio::log.info "Zápisové endpointy vyžadujú API token"
else
    bashio::log.warning "api_token nie je nastavený – ktokoľvek v sieti môže nahrávať a mazať fotky"
fi

python3 /usr/bin/watcher.py
