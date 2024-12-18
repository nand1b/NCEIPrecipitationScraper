import json
import queue
import time
import traceback
from json import JSONDecoder
from time import sleep

import selenium
import selenium.webdriver
import shutil
import os

from selenium.webdriver import ActionChains
from selenium.webdriver.common.by import By
from selenium.webdriver.common.devtools.v85.dom import scroll_into_view_if_needed
from selenium.webdriver.remote.webelement import WebElement
from selenium.webdriver.support.select import Select
from selenium.webdriver.support.wait import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

def wait_for_vis(driver, target_id, timeout=10, by_val=By.CSS_SELECTOR):
    wait = WebDriverWait(driver, timeout)
    ret = wait.until(EC.visibility_of_element_located((by_val, target_id)))
    return ret

def wait_and_get(driver, target_id, timeout=10, by_val=By.ID):
    wait = WebDriverWait(driver, timeout)
    return wait.until(EC.presence_of_element_located( (by_val, target_id) ))

def wait_and_get_vis_vals(driver, target_id, timeout=10, by_val=By.ID):
    wait = WebDriverWait(driver, timeout)
    return wait.until(EC.visibility_of_all_elements_located( (by_val, target_id) ))

def make_selection(driver, list_name, visible_choice):
    select = Select(wait_and_get(driver, list_name))

    # wait for option to be present or timeout
    wait = WebDriverWait(driver, 10)
    is_choice_present = lambda d : is_option_present(select, visible_choice)
    wait.until(is_choice_present)

    select.select_by_visible_text(visible_choice)

def is_option_present(select : Select, visible_choice):
    for element in select.options:
        if element.text == visible_choice:
            return True

def is_downloading(driver):
    top_download : WebElement = get_top_download(driver)
    curr_down_desc : list[WebElement] = top_download.shadow_root.find_elements(By.CSS_SELECTOR, "div[class='description']")
    for element in curr_down_desc:
        if element.is_displayed():
            return True

    return False

# spread out for debugging purposes; assumes driver is on chrome downloads url already
def get_top_download(driver):
    curr_down : WebElement = wait_and_get(driver, "//downloads-manager", by_val=By.XPATH)
    curr_down = curr_down.shadow_root.find_element(value="downloadsList") # does find shadow root
    curr_down = curr_down.find_element(value="list")
    curr_down = curr_down.find_element(value="frb0")
    return curr_down

def initialize_driver(down_dir):
    # ensure files downloaded to correct location
    options = selenium.webdriver.ChromeOptions()
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-setuid-sandbox")

    options.add_argument("--remote-debugging-port=9222")  # this

    options.add_argument("--disable-dev-shm-using")
    options.add_argument("--disable-extensions")
    options.add_argument("--disable-gpu")
    options.add_argument("start-maximized")
    options.add_argument("disable-infobars")
    options.add_argument(r"user-data-dir=.\cookies\\test")
    prefs = {"download.default_directory": down_dir, "profile.managed_default_content_settings.images": 2}
    options.add_experimental_option("prefs", prefs)

    # start driver
    return selenium.webdriver.Chrome(options=options)

def data_downloader(parameter, months, year_start, year_end, county_list, driver):
    for county in county_list:
        for month in months:
            driver.get("https://www.ncei.noaa.gov/access/monitoring/climate-at-a-glance/county/time-series")
            # time.sleep(5) # website does not like when you grab data before its done loading the first plot
            try:
                # select each category and the desired option
                make_selection(driver, 'parameter', parameter)
                make_selection(driver, 'timescale', 'Year-to-Date')
                make_selection(driver, 'month', month)
                make_selection(driver, 'begyear', str(year_start))
                make_selection(driver, 'endyear', str(year_end))
                make_selection(driver, 'state', 'California')
                make_selection(driver, 'location', county)

                # have website create link
                button = wait_for_vis(driver, "input[value=\'Plot\']", by_val=By.CSS_SELECTOR)
                # time.sleep(2)  # if you don't wait on the button it errors out
                button.click()  # Create data link

                # get link
                link = wait_for_vis(driver, "//span[@id=\'data-access\']/a[@id=\'json-download\']", by_val=By.XPATH)
                ActionChains(driver).scroll_to_element(link).perform()  # must be in view
                link.click()  # download the csv file

                # wait for download before reloading page
                driver.get("chrome://downloads")  #
                try:
                    while is_downloading(driver):
                        sleep(2)  # wait for download to finish
                except Exception as e:
                    print("Got Exception checking downloads of: \n")
                    e.with_traceback()

            except Exception as e:
                print("Got Exception: \n")
                e.with_traceback()
                print(" -for {" + parameter + ", " + month + ", " + county + "}.")

            # month loop last line

        # county loop last line

    driver.close()


def data_parser(parameter, months, year_start, year_end, county_list, down_dir, month_dict):
    # now that all downloads have completed, parsing must be done
    out_dir = os.path.join(os.path.dirname(os.path.realpath(__file__)), "output")
    month_count: int = len(months)
    county_count: int = len(county_list)

    if not os.path.exists(out_dir):
        os.makedirs(out_dir)

    for month_index in range(0, month_count):
        month = months[month_index]
        out_path = os.path.join(out_dir,
                                parameter + ": " + month + ", " + str(year_start) + "-" + str(year_end) + ".csv")

        # create file if necessary
        if not os.path.exists(out_path):
            open(out_path, 'x').close()

        # write to csv
        with open(out_path, 'w') as file:

            # all counties go into one file based on month
            for county_index in range(0, county_count):
                src_filename = "data"
                if month_index > 0 or county_index > 0:
                    src_filename += " (" + str(county_index * month_count + month_index) + ")"

                src_filename += ".json"

                # assume that data exists and try to read it
                src_file = open(os.path.join(down_dir, src_filename))
                data = json.load(src_file)
                data = data["data"]
                src_file.close()

                county_data = county_list[county_index]

                # go through all data points and add them alongside the preceding comma
                for year in range(year_start, year_end + 1):
                    county_data += ", " + data[str(year) + str(month_dict[month.lower()])]["value"]

                # add new line and write now that all year values have been covered
                file.write(county_data + '\n')

                # last line of county loop

            # last line of file reading

        # last line of month loop

    # last line of parser

def data_grabber():
    # inclusive start and end dates
    parameter = "Precipitation"
    months = ["December"] # capitalization is irrelevant
    month_dict : dict[str, int] = { "january" : 1, "february" : 2, "march" : 3, "april" : 4, "may" : 5, "june" : 6, "july" : 7,
                   "august" : 8, "september" : 9, "october" : 10, "november" : 11, "december" : 12}
    year_start = 1985
    year_end = 2023
    county_list : list[str] = [] # empty indicates all
    skip_download = False # if you already have the data and just want to parse it

    # create the path for all the files for any given year range and parameter to be downloaded
    down_dir = os.path.join(os.path.dirname(os.path.realpath(__file__)), "data", parameter, str(year_start) + "-" + str(year_end))

    # do all the driver initialization things
    driver = initialize_driver(down_dir)
    driver.get("https://www.ncei.noaa.gov/access/monitoring/climate-at-a-glance/county/time-series")

    # check if county list is empty wait and get all elements in list
    if len(county_list) == 0:
        driver.implicitly_wait(2)  # give the page some time to load just in case
        make_selection(driver, 'state', 'California')  # get counties from correct state
        driver.implicitly_wait(3)

        for county_element in Select(wait_and_get(driver, 'location')).options:
            county_list.append(county_element.text)

    county_list.sort()
    months.sort(key=lambda month_name: month_dict[month_name.lower()])  # sort by order in year just in case user didnt

    if not skip_download:
        data_downloader(parameter, months, year_start, year_end, county_list, driver)

    data_parser(parameter, months, year_start, year_end, county_list, down_dir, month_dict)

    # grabber last line


if __name__ == '__main__':
    try:
        data_grabber()
    except Exception as e:
        # printl("PrecipitationGrabber execution failed; printing exception: \n" + str(e))
        # printl("Full stack trace \n")
        traceback.print_exc()