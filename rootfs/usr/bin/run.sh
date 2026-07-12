#!/usr/bin/with-contenv bashio

SMB_SERVER=$(bashio::config 'smb_server')
SMB_SHARE=$(bashio::config 'smb_share')
SMB_USERNAME=$(bashio::config 'smb_username')
SMB_PASSWORD=$(bashio::config 'smb_password')
WATCH_FOLDER=$(bashio::config 'watch_folder')
OUTPUT_FOLDER=$(bashio::config 'output_folder')
DELETE_ORIGINAL=$(bashio::config 'delete_original')
JPG_QUALITY=$(bashio::config 'jpg_quality')
THUMB_QUALITY=$(bashio::config 'thumb_quality')
THUMB_MAX_PX=$(bashio::config 'thumb_max_px')
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

# bashio vracia "null" pre nové polia ktoré ešte nie sú v options – nahraď defaultmi
[ "${THUMB_QUALITY}" = "null" ]      && THUMB_QUALITY="82"
[ "${THUMB_MAX_PX}" = "null" ]       && THUMB_MAX_PX="1024"
[ "${BASIC_AUTH_USER}" = "null" ]    && BASIC_AUTH_USER=""
[ "${BASIC_AUTH_PASSWORD}" = "null" ] && BASIC_AUTH_PASSWORD=""
[ "${LANGUAGE}" = "null" ]            && LANGUAGE="sk"
[ "${SLEEP_START}" = "null" ]         && SLEEP_START=""
[ "${SLEEP_END}" = "null" ]           && SLEEP_END=""
[ "${WEATHER_PHOTO_INTERVAL}" = "null" ]    && WEATHER_PHOTO_INTERVAL="8"
[ "${WEATHER_MODE_DURATION_MIN}" = "null" ] && WEATHER_MODE_DURATION_MIN="120"

bashio::log.info "SMB server: ${SMB_SERVER}"
bashio::log.info "SMB share: ${SMB_SHARE}"
bashio::log.info "Watch folder: ${WATCH_FOLDER}"
bashio::log.info "Output folder: ${OUTPUT_FOLDER}"
bashio::log.info "Delete original: ${DELETE_ORIGINAL}"
bashio::log.info "Scan interval (hours): ${SCAN_INTERVAL_HOURS}"
bashio::log.info "Thumbnail: max ${THUMB_MAX_PX}px, kvalita ${THUMB_QUALITY}"

if [ -z "${SMB_USERNAME}" ] || [ -z "${SMB_PASSWORD}" ]; then
    bashio::log.error "smb_username alebo smb_password nie je nastavené v konfigurácii. Add-on sa zastavuje."
    exit 1
fi

mkdir -p /sambamount

CRED_FILE=$(mktemp)
chmod 600 "${CRED_FILE}"
{
    echo "username=${SMB_USERNAME}"
    echo "password=${SMB_PASSWORD}"
} > "${CRED_FILE}"

bashio::log.info "Pripájam CIFS share //${SMB_SERVER}/${SMB_SHARE} na /sambamount..."
mount -t cifs "//${SMB_SERVER}/${SMB_SHARE}" /sambamount \
    -o "credentials=${CRED_FILE},vers=3.0,iocharset=utf8,file_mode=0660,dir_mode=0770,uid=0,gid=0"
MOUNT_RESULT=$?

shred -u "${CRED_FILE}" 2>/dev/null || rm -f "${CRED_FILE}"

if [ ${MOUNT_RESULT} -ne 0 ]; then
    bashio::log.error "Pripojenie CIFS zlyhalo! Skontroluj smb_server, smb_username a smb_password v konfigurácii."
    sleep 30
    exit 1
fi

bashio::log.info "CIFS pripojené úspešne."

mkdir -p "${WATCH_FOLDER}"
mkdir -p "${OUTPUT_FOLDER}"
mkdir -p /data

export WATCH_FOLDER
export OUTPUT_FOLDER
export DELETE_ORIGINAL
export JPG_QUALITY
export THUMB_QUALITY
export THUMB_MAX_PX
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
export PYTHONPATH="/usr/bin:${PYTHONPATH:-}"

bashio::log.info "Slideshow interval: ${SLIDESHOW_SECONDS} s"
bashio::log.info "Web port: ${WEB_PORT}"
if [ -n "${BASIC_AUTH_USER}" ]; then
    bashio::log.info "HTTP Basic Auth zapnutá pre: ${BASIC_AUTH_USER}"
fi

python3 /usr/bin/watcher.py
