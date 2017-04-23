'''
nimbus
@ningOTI, ningyuan.sg@gmail.com
'''
import os, sys, time, csv, json, logging
import requests, bs4, tweepy, imageio
from PIL import Image, ImageFont, ImageDraw

PATH = sys.path[0] + '/'
RESOURCES_PATH = PATH + 'resources/'
FONT_PATH = RESOURCES_PATH + 'Aileron-Regular.otf'
MASK_PATH = RESOURCES_PATH + 'mask.png'
LEGEND_PATH = RESOURCES_PATH + 'legend.png'
TOWNSHIPMAP_PATH = RESOURCES_PATH + 'townshipmap_compressed.png'
CONFIG_PATH = PATH + 'config.json'
HISTORY_PATH = PATH + 'history.csv'
OVERLAY_PATH = PATH + 'overlay.png'
OVERLAID_PATH = PATH + 'overlaid.png'
MAP_HISTORY_PATH = PATH + 'map_histories/'

logging.basicConfig(
        filename=PATH+'sgraincloud.log',
        level=logging.WARNING,
        format='[%(asctime)s] %(levelname)s - %(message)s',
        datefmt='%d/%m/%y %H:%M:%S')
logging.getLogger('requests').setLevel(logging.WARNING)
logging.getLogger('tweepy').setLevel(logging.WARNING)

assert os.path.isfile(FONT_PATH)         # compulsory--font @ resources/Aileron-Regular.otf
assert os.path.isfile(MASK_PATH)         # compulsory--mask @ resources/mask.png
assert os.path.isfile(LEGEND_PATH)       # compulsory--legend @ resources/legend.png
assert os.path.isfile(TOWNSHIPMAP_PATH)  # compulsory--bare map @ resources/townshipmap_compressed.png

# SCRIPT INITIATION (history.csv)
if not os.path.isfile(HISTORY_PATH):
    with open(HISTORY_PATH, 'w', newline='') as file:
        # CSV in the format datetime, rain percent, tweet id(?)
        writer = csv.writer(file)
        writer.writerow(['nil', '0', '0'])
if not os.path.isdir(MAP_HISTORY_PATH):
    os.makedirs(MAP_HISTORY_PATH)

# SCRIPT INITIATION (config.json)
if not os.path.isfile(CONFIG_PATH):
    with open(CONFIG_PATH, 'w') as file:
        json.dump(
            {
                'consumer_key': '',
                'consumer_secret': '',
                'access_token': '',
                'access_token_secret': '',
                'bot_id': '',
                'handler_id': '',
                'reddit_username': '',
                'reddit_password': ''
            },
            file,
            indent=4
        )
    sys.stdout('No config.json detected;\nNew config.json created;')
    quit()
else:
    with open(CONFIG_PATH, 'r') as file:
        file_dump = file.read()
        config_json = json.loads(file_dump)

class weathergov:
    def __init__(self):
        self.url = 'http://www.weather.gov.sg/weather-rain-area-50km/'
        self.html = requests.get(self.url)
        self.soup = bs4.BeautifulSoup(self.html.text, 'html.parser')

        self.datetime_selector = 'p#issueDate'
        self.datetime = self.soup.select(self.datetime_selector)[0].string
        self.datetime_minutes = self.datetime.split()[0][-2:]
        
        self.overlay_url_selector = 'img#picture'
        self.overlay_url = self.soup.select(self.overlay_url_selector)[0].get('src')
        self.overlay_data = requests.get(self.overlay_url)

        with open(HISTORY_PATH, 'r') as file:
            reader = csv.reader(file)
            self.history_csv = list(reader)

        self.reverse_history = list(reversed(self.history_csv))

    # I would rather have a function that returns self.overlay_data, but PIL.Image doesn't work like that
    # TODO: ask stack overlay if possible to pass requests.models.Response to PIL.Image
    # TODO: learn it (seems complicated)
    def save_overlay(self):
        with open(OVERLAY_PATH, 'wb') as file:
            for chunk in self.overlay_data.iter_content(10000):
                file.write(chunk)

    def clean_map_histories(self):
        history_files = os.listdir(MAP_HISTORY_PATH)
        logging.debug('rem_old: initial listdir count as %s' % str(len(os.listdir(MAP_HISTORY_PATH))))
        for history in history_files:
            ctime = os.path.getctime(MAP_HISTORY_PATH + history)
            if time.time() - ctime > 86400:  # older than 24hrs
                os.remove(MAP_HISTORY_PATH + history)
        logging.debug('rem_old: last listdir count as %s' % str(len(os.listdir(MAP_HISTORY_PATH))))

    def update_history(self, datetime='nil', alpha_ratio='nil', twt_id='nil'):
        with open(HISTORY_PATH, 'w', newline='') as file:
            writer = csv.writer(file)
            if len(self.history_csv) > 300:
                logging.info('history_csv exceeding, deleting entry')
                del self.history_csv[0]
            writer.writerows(self.history_csv)
            writer.writerow([
                datetime,
                alpha_ratio,
                twt_id
                ])

            
class SGRC_API():
    def __init__(self):
        self.consumer_key = config_json['consumer_key']
        self.consumer_secret = config_json['consumer_secret']
        self.access_token = config_json['access_token']
        self.access_token_secret = config_json['access_token_secret']
        self.bot_id = config_json['bot_id']

        self.auth = tweepy.OAuthHandler(self.consumer_key, self.consumer_secret)
        self.auth.set_access_token(self.access_token, self.access_token_secret)
        self.API = tweepy.API(self.auth)

        self.handler = config_json['handler_id']

    def pm_handler(self, msg):
        self.API.send_direct_message(
                user_id=self.handler,
                text=msg)

    def tweet_media(self, media):
        media = self.API.media_upload(media)
        self.API.update_status(media_ids=[media.media_id_string])

    def tweet_media_msg(self, media, msg):
        media = self.API.media_upload(media)
        self.API.update_status(status=msg, media_ids=[media.media_id_string])

    def get_twt_id(self):
        return self.API.user_timeline(self.bot_id, count=1)[0].id


class Image_Handler():
    def __init__(self):
        self.sgmap = Image.open(TOWNSHIPMAP_PATH)
        self.legend = Image.open(LEGEND_PATH)
        self.overlay = Image.open(OVERLAY_PATH)
        self.overlay_pao = self.overlay.load()
        self.mask = Image.open(MASK_PATH)
        self.mask_pao = self.mask.load()
        self.mask_xy = []

        for x in range(self.mask.size[0]):
            for y in range(self.mask.size[1]):
                if self.mask_pao[x,y][3] != 0:
                    self.mask_xy.append((x,y))

    def generate(self, datetime):
        for x in range(self.overlay.size[0]):
            for y in range(self.overlay.size[1]):
                self.overlay_pao[x, y] = (
                        self.overlay_pao[x, y][0],
                        self.overlay_pao[x, y][1],
                        self.overlay_pao[x, y][2],
                        int(self.overlay_pao[x, y][3] / 2))

        overlay_resize = self.overlay.resize((self.sgmap.size[0], self.sgmap.size[1]), Image.ANTIALIAS)
        self.sgmap.paste(overlay_resize, (0, 0), overlay_resize)

        font = ImageFont.truetype(font=FONT_PATH, size=30)
        draw_image = ImageDraw.Draw(self.sgmap)
        draw_image.text((20, 20), datetime, font=font, fill=(0, 0, 0, 255))

        self.sgmap.save(MAP_HISTORY_PATH+datetime+'.png', optimise=True, quality=50)

        self.sgmap.paste(self.legend, (1050, 750))
        self.sgmap.save(OVERLAID_PATH, optimise=True, quality=95)

    def percent_alpha(self):
        total_pixel_count = 0
        opaque_pixel_count = 0

        for x in range(self.overlay.size[0]):
            for y in range(self.overlay.size[1]):
                total_pixel_count += 1
                if self.overlay_pao[x, y][3] != 0:
                    opaque_pixel_count +=1

        return opaque_pixel_count / total_pixel_count
        
    def percent_alpha_mask(self):
        total_pixel_count = len(self.mask_xy)
        opaque_pixel_count = 0

        for coord in self.mask_xy:
            if self.overlay_pao[coord][3] != 0:
                opaque_pixel_count += 1

        return opaque_pixel_count / total_pixel_count

    def gen_gif(self, datetime_list, export_name):
        kwargs_write = {'fps':7.5,
                'quantizer':'nq',  # default wu, but nq works better
                'palettesize': 16}  # default 256 (max), but file size too large
        frames = []
        for datetime in datetime_list:
            frames.append(imageio.imread(MAP_HISTORY_PATH+datetime+'.png'))#, **kwargs_read))
        imageio.mimsave(MAP_HISTORY_PATH+export_name, frames, 'GIF-FI', **kwargs_write)  # if 'GIF'default'GIF-PIL'
        
def main():
    weather = weathergov()
    API = SGRC_API()

    # start of if-else for deciding if this datetime is new (if site has updated)
    if weather.datetime not in weather.history_csv[-1]:
        logging.info('Detected change in datetime: %s' % weather.datetime)
        weather.save_overlay()
        logging.debug('overlay.png written to dir')

        # ImHandler must be created after new overlay.png is saved so the
        # __init__ self.overlay Image object will be up-to-date
        ImHandler = Image_Handler()
        ImHandler.generate(weather.datetime)
        logging.debug('overlaid.png generated')
        alpha_ratio = ImHandler.percent_alpha_mask()

        rain_cover = alpha_ratio > 0.01

        # start of if-else for deciding if update should be tweeted
        if (
                ((not rain_cover) and (weather.datetime_minutes == '00')) or
                (rain_cover) or
                ((not rain_cover) and (float(weather.history_csv[-1][1]) > 0.01))
                ):
            API.tweet_media(OVERLAID_PATH)
            logging.info('Tweeted with updated sgmap of %s' % weather.datetime)
            weather.update_history(datetime=weather.datetime,
                    alpha_ratio=alpha_ratio,
                    twt_id=API.get_twt_id())

        else:
            logging.info('Update of datetime %s not tweeted' % weather.datetime)
            weather.update_history(datetime=weather.datetime,
                    alpha_ratio=alpha_ratio)

        weather.clean_map_histories()

        logging.debug('Starting gif logic...')
        # start of if-else for deciding if gif should be created 
        rain_list = []
        rain_stopped = False
        reverse_history_index0_alpha = float(weather.reverse_history[0][1])
        reverse_history_index1_alpha = float(weather.reverse_history[1][1])
        # rain just stopped: latest no rain, second latest rain
        if reverse_history_index0_alpha <= 0.01 and reverse_history_index1_alpha > 0.01:
            rain_stopped = True
            logging.debug('conditional hit: rain stopped')
            for i in range(len(weather.reverse_history)-1):
                if float(weather.reverse_history[i+1][1]) > 0.01:
                    rain_list.append(weather.reverse_history[i][0])
                else: 
                    break
        # still raining
        elif reverse_history_index0_alpha > 0.01:
            logging.debug('conditional hit: still raining')
            for i in weather.reverse_history:
                if float(i[1]) > 0.01:
                    rain_list.append(i[0])
                else:
                    break

        logging.info('rain_list of length %s generated' % str(len(rain_list)))

        # only for substantial rains, i.e. longer than 30mins 6*5=30
        if len(rain_list) > 5:
            rain_string = '{} to {}'.format(
                    ''.join(rain_list[-1].split()[:2]),
                    ''.join(rain_list[0].split()[:2]))
            export_name = rain_string + '.gif'
            logging.debug('conditional hit: rain_list > 5')
            logging.debug('first datetime %s second datetime %s' % (rain_list[0], rain_list[-1]))
            # if the rain has just stopped
            if rain_stopped:
                logging.debug('conditional hit: rain_stopped')
                logging.info('gif generation starting for %s' % export_name)
                ImHandler.gen_gif(list(reversed(rain_list)), export_name)
                logging.debug('gen_gif passed')
                API.tweet_media_msg(export_name, "The skies have cleared! Here's a summary, from {}.".format(rain_string))
                weather.update_history(datetime=rain_string,
                        alpha_ratio='rain stopped',
                        twt_id=API.get_twt_id())

            # rain ongoing, but it has been a half hour interval since it started
            elif len(rain_list) % 6 == 0:
                logging.debug('conditional hit: half hour interval on rain')
                logging.info('gif generation starting for %s' % export_name)
                ImHandler.gen_gif(list(reversed(rain_list)), export_name)
                logging.debug('gen_gif passed')
                API.tweet_media_msg(export_name, "It's raining! Here's a summary, from {}.".format(rain_string))
                weather.update_history(datetime=rain_string,
                        alpha_ratio='rain ongoing',
                        twt_id=API.get_twt_id())

    else:
        logging.debug('No change detected')

if __name__ == '__main__':
    main()
