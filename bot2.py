from telegram import *
from telegram.ext import *
import logging
import configparser
from pymongo import MongoClient
from datetime import datetime, timedelta
import random
import certifi
import os
import sys
import fcntl


def acquire_lock():
    lock_file_path = './lockfile.lock'

    # Check if the lock file already exists (another instance is running)
    if os.path.isfile(lock_file_path):
        print("Another instance is already running. Exiting.")
        sys.exit(1)

    # Create the lock file and acquire the lock
    lock_file = open(lock_file_path, 'w')
    try:
        fcntl.lockf(lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
        print("Lock acquired. Bot instance is running.")
    except IOError:
        print("Unable to acquire lock. Another instance is already running. Exiting.")
        sys.exit(1)


def release_lock():
    lock_file_path = '/path/to/your/lockfile.lock'
    try:
        os.unlink(lock_file_path)
        print("Lock released. Bot instance has finished.")
    except Exception as e:
        print("Error releasing lock:", e)


# Config
config = configparser.ConfigParser()
config.read("config.ini")
# Telegram chatbot token
TOKEN = config.get("default", "bot_token")
USERNAME = config.get("default", "username")
PASSWORD = config.get("default", "password")
COLLECTION_NAME_MAIN = config.get("default", "collection_name_main")
COLLECTION_NAME_SEC = config.get("default", "collection_name_sec")
DATABASE_NAME = config.get("default", "db_name")

# Mongo urls
url = "mongodb+srv://" + USERNAME + ":" + PASSWORD + \
    "@miniurl.jdm3ikb.mongodb.net/?retryWrites=true&w=majority"
cluster = MongoClient(url, tlsCAFile=certifi.where())


# Enable logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
# set higher logging level for httpx to avoid all GET and POST requests being logged
logging.getLogger("httpx").setLevel(logging.WARNING)

logger = logging.getLogger(__name__)

# Defining states (numerical values for chatbot)
END = ConversationHandler.END
REFRESH = -2
SELECT_ACTION = map(chr, range(0, 1))

# Defining states for gym plan
ADD_PLAN, REMOVE_PLAN, EDIT_PLAN = map(chr, range(1, 4))

ADD_DAY, REMOVE_DAY = map(chr, range(4, 6))

# Show a plan, stop current action
SHOWING, RESTART = map(chr, range(6, 8))

# Defining states for recipes
ADD_RECIPE, DELETE_RECIPE, SHOW_RECIPES = map(chr, range(8, 11))

SELECT_GYM_PLAN_ACTION, SELECT_RECIPE_ACTION = map(chr, range(11, 13))

CLOCK_WORKOUT = chr(13)

BACK, ARMS, LEGS, CHEST, SHOULDERS, ABS, REST_DAY, NEXT_DAY = map(
    chr, range(14, 22))

FINISH_ADD_PLAN, FINISH_EDIT_PLAN, CONFIRM_REMOVE, ABORT_REMOVE = map(
    chr, range(22, 26))

MON, TUES, WED, THURS, FRI, SAT, SUN = map(chr, range(26, 33))

COMPLETED_WORKOUT, ALT_WORKOUT, INCOMPLETE_WORKOUT = map(
    chr, range(33, 36))
# 36 is $ which regex will read as EOL
FINISH_CLOCK_WORKOUT = chr(36)


async def start(update, context) -> str:
    text = ("You can choose to work on your gym plan, or work on some tasty recipes. To restart, type /refresh. To end this convo, type /stop. To get help, type /help.")

    buttons = [[InlineKeyboardButton(text="Gym plan", callback_data=str(SELECT_GYM_PLAN_ACTION))], [
        InlineKeyboardButton(text="Recipes", callback_data=str(SELECT_RECIPE_ACTION))]]

    keyboard = InlineKeyboardMarkup(buttons)
    if context.user_data.get(RESTART):
        await update.callback_query.answer()
        await update.callback_query.edit_message_text(text=text, reply_markup=keyboard)
    else:
        await update.message.reply_text("Hi King, I'm GymPlanBot and I'm here to help you get ripped")
        await update.message.reply_text(text=text, reply_markup=keyboard)
    return SELECT_ACTION


async def stop(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = "See you again King!"
    await update.message.reply_text(text=text)
    return END


async def helper(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("Placeholder for message")


async def refresh_nested(update: Update, context: ContextTypes.DEFAULT_TYPE) -> str:
    await update.message.reply_text("Restarting operation. Type /continue to confirm refresh")
    return REFRESH


def get_current_plan(chat_id):
    current_day = datetime.now()
    temp_plan = temp_plans.find_one({"user_id": chat_id})
    main_plan = main_plans.find_one({"user_id": chat_id})
    if not temp_plan:
        return main_plan
    else:
        time_diff = current_day - temp_plan["timestamp"]
        if time_diff >= timedelta(days=7):
            return main_plan
        else:
            return temp_plan


def prettify(plan):
    res = ""
    for k, v in plan.items():
        res += f"{k}: "
        for i in range(0, len(v) - 1):
            res += f"{v[i]}, "
        res += f"{v[-1]}\n"
    return res


async def gym_plan_options(update: Update, context: ContextTypes.DEFAULT_TYPE, edited=False) -> str:
    chat_id = update.effective_chat.id
    global has_plan, displayed_plan
    # If can find workout plan of chat id, return it
    # If there exists a temporary plan for the next 7 days, use it instead
    # Temporary plans expire after 7 days from creation
    workout_plan = displayed_plan if displayed_plan and not edited else get_current_plan(
        chat_id)
    if workout_plan and (not has_plan or edited):
        has_plan = True
        displayed_plan = workout_plan
        del displayed_plan["_id"]
        del displayed_plan["user_id"]
        if "timestamp" in displayed_plan:
            del displayed_plan["timestamp"]
    buttons = []
    text = ""
    if has_plan:
        buttons.append([InlineKeyboardButton(
            text="Edit Plan", callback_data=str(EDIT_PLAN))])
        buttons.append([InlineKeyboardButton(
            text="Remove Plan", callback_data=str(REMOVE_PLAN))])
        buttons.append([InlineKeyboardButton(
            text="Clock Workout", callback_data=str(CLOCK_WORKOUT))])
        text += "Here is your current gym plan: \n"
        text += prettify(workout_plan)
    else:
        buttons.append([InlineKeyboardButton(
            text="Add Plan", callback_data=str(ADD_PLAN))])
        text += "Create a gym plan now!"

    keyboard = InlineKeyboardMarkup(buttons)

    await update.callback_query.answer()
    await update.callback_query.edit_message_text(text=text, reply_markup=keyboard)

    return SELECT_GYM_PLAN_ACTION


async def recipe_options(update: Update, context: ContextTypes.DEFAULT_TYPE) -> str:

    pass


# Clocking of workout only gives a temporary plan (still needs to be read from somewhere)
async def clock_workout(update: Update, context: ContextTypes.DEFAULT_TYPE) -> str:
    global alt_workouts, available_types, displayed_plan
    if update.callback_query.data == CLOCK_WORKOUT:
        if not has_plan:
            logger.error(
                "Clocking workout should only be visible if workout exists")
            return await gym_plan_options(update, context)
        text = "So how was your workout today?"
        buttons = [[InlineKeyboardButton(text="Completed my workout!", callback_data=str(COMPLETED_WORKOUT)), InlineKeyboardButton(
            text="Did something else", callback_data=str(ALT_WORKOUT)), InlineKeyboardButton(text="I'm noob and did nothing", callback_data=str(INCOMPLETE_WORKOUT))]]
        keyboard = InlineKeyboardMarkup(buttons)
        await update.callback_query.answer()
        await update.callback_query.edit_message_text(text=text, reply_markup=keyboard)

    elif update.callback_query.data == COMPLETED_WORKOUT:
        await update.callback_query.edit_message_text(text="Good job KING! Remember to stay consistent!")
        return await gym_plan_options(update, context)
    elif update.callback_query.data == ALT_WORKOUT:
        text = "Which workouts did you do?"
        buttons = []
        for i, j in available_types.items():
            buttons.append(
                [InlineKeyboardButton(text=i, callback_data=str(j))])
        keyboard = InlineKeyboardMarkup(buttons)
        await update.callback_query.answer()
        await update.callback_query.edit_message_text(text=text, reply_markup=keyboard)

    elif update.callback_query.data == INCOMPLETE_WORKOUT:
        text = "Ok KING, there is always tomorrow! Let's see what I can do for you for the time being..."
        # TODO: Fetch gym plan
        displayed_plan = remake(displayed_plan)
        new_entry = displayed_plan.copy()
        new_entry["user_id"] = update.effective_chat.id
        new_entry["timestamp"] = datetime.now()
        if temp_plans.find_one({"user_id": update.effective_chat.id}):
            temp_plans.delete_one({"user_id": update.effective_chat.id})
        temp_plans.insert_one(new_entry)
        return await gym_plan_options(update, context)
    elif update.callback_query.data in map(chr, range(14, 21)):
        text = "What other workout(s) did you do?"
        buttons = []
        val_index = list(available_types.values()).index(
            update.callback_query.data)
        workout = list(available_types.keys())[val_index]
        alt_workouts.append(workout)
        if update.callback_query.data == REST_DAY:
            return await finish_clock_workout(update, context)
        available_types.pop(workout)
        available_types.pop("Rest")
        if len(available_types) != 0:
            # No more workout types to add
            for i, j in available_types.items():
                buttons.append(
                    [InlineKeyboardButton(text=i, callback_data=str(j))])
        buttons.append([InlineKeyboardButton(
            text="Finish", callback_data=str(FINISH_EDIT_PLAN))])
        keyboard = InlineKeyboardMarkup(buttons)
        await update.callback_query.answer()
        await update.callback_query.edit_message_text(text=text, reply_markup=keyboard)
    else:
        logger.error("Not supposed to reach here!")
    return CLOCK_WORKOUT


async def finish_clock_workout(update: Update, context: ContextTypes.DEFAULT_TYPE) -> str:
    global displayed_plan, alt_workouts, available_types, workout_types
    # TODO: Fetch gym plan and alter based on given workouts, then reset available types & alt_workouts
    # If there is already a temp plan for the week, will reset the temp plan with a new temp plan
    displayed_plan = remake(displayed_plan, alt_workouts)
    # Print it out for the user to see ltr
    alt_workouts.clear()
    available_types = workout_types.copy()
    # user has no prior temp plans
    new_entry = displayed_plan.copy()
    new_entry["user_id"] = update.effective_chat.id
    new_entry["timestamp"] = datetime.now()
    if temp_plans.find_one({"user_id": update.effective_chat.id}):
        temp_plans.delete_one({"user_id": update.effective_chat.id})
    temp_plans.insert_one(new_entry)
    return await gym_plan_options(update, context)

alt_workouts = []


def remake(workouts, alt_workouts=[]):
    # If the user did not do anything that day [self-proclaimed rest day]
    curr_day = datetime.now().strftime("%a")
    original_workouts = workouts[curr_day]
    if "Rest" in original_workouts:
        if len(alt_workouts) == 0:
            pass
        else:
            # Worked on a rest day
            workouts = removeEarliest(workouts, alt_workouts, curr_day)

    else:
        # Rested on a work day
        if len(alt_workouts) == 0:
            # Can include 1 rest day if illegible
            workouts = distributeToOthers(
                workouts, original_workouts, curr_day)
        else:
            workouts = replaceAndDistribute(
                workouts, original_workouts, alt_workouts, curr_day)
    return workouts


def removeEarliest(workouts, alt_workouts, curr_day):
    global days
    day_index = days.index(curr_day)
    search_list = []
    next_day_index = (day_index + 1) % 7
    while next_day_index != day_index:
        search_list.append(days[next_day_index])
        next_day_index = (next_day_index + 1) % 7
    for d in search_list:
        d_day_workouts = set(workouts[d])
        alt_workout_set = set(alt_workouts)
        remainder_d = list(d_day_workouts.difference(alt_workout_set))
        remainder_alt = list(alt_workout_set.difference(d_day_workouts))
        if len(remainder_d) == 0:
            # sacrifice rest day, so given more rest days if possible
            workouts[d] = ["Rest"]
        else:
            workouts[d] = remainder_d
        if len(remainder_alt) == 0:
            return workouts
        else:
            alt_workouts = remainder_alt
    return workouts


def distributeToOthers(workouts, original_workouts, curr_day):
    workout_list = []
    for i, j in workouts.items():
        workout_list.append((i, j))
    distribution_map = {}
    for w in original_workouts:
        distribution_map[w] = []
        for i in range(len(workout_list)):
            if workout_list[i][0] == curr_day:
                continue
            isTooCommonAndNotAroundCurr = workout_list[(i - 1) % 7][0] != curr_day and workout_list[(i + 1) % 7][0] != curr_day and (
                w in workout_list[(i - 1) % 7][1] or w in workout_list[(i + 1) % 7][1] or w in workout_list[i][1])
            isTooCommonButAroundCurr = w in workout_list[i][1] or (w in workout_list[(i - 1) % 7][1] and workout_list[(
                i - 1) % 7][0] != curr_day) or (w in workout_list[(i + 1) % 7][1] and workout_list[(i + 1) % 7][0] != curr_day)
            if not (isTooCommonAndNotAroundCurr and isTooCommonButAroundCurr):
                distribution_map[w].append(workout_list[i][0])
    # After this point, each has a possible day we can put the workout in
    for i, j in distribution_map.items():
        day = random.choice(j)
        if "Rest" in workouts[day]:
            workouts[day] = [i]
        else:
            workouts[day].append(i)
    return workouts


def replaceAndDistribute(workouts, original_workouts, alt_workouts, curr_day):
    # Hybrid version of above 2 functions.
    original_set = set(original_workouts)
    alt_set = set(alt_workouts)
    replaced_list = list(original_set.difference(alt_set))
    replacement_list = list(alt_set.difference(original_set))
    workouts = removeEarliest(workouts, replacement_list, curr_day)
    workouts = distributeToOthers(workouts, replaced_list, curr_day)
    return workouts


final_workouts = {
    "Mon": [],
    "Tue": [],
    "Wed": [],
    "Thu": [],
    "Fri": [],
    "Sat": [],
    "Sun": [],
}

workout_types = {"Back": BACK, "Legs": LEGS, "Chest": CHEST,
                 "Arms": ARMS, "Abs": ABS, "Shoulders": SHOULDERS, "Rest": REST_DAY}
available_types = workout_types.copy()
days = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
day_mappings = {"Mon": MON, "Tue": TUES, "Wed": WED,
                "Thu": THURS, "Fri": FRI, "Sat": SAT, "Sun": SUN}
curr_day = 0
has_plan = False
displayed_plan = None


async def add_workout(update: Update, context: ContextTypes.DEFAULT_TYPE) -> str:
    buttons = []
    text = ""
    global final_workouts, workout_types, available_types, days, curr_day
    if update.callback_query.data == FINISH_ADD_PLAN:
        return ADD_PLAN
    # Initial load
    if update.callback_query.data == ADD_PLAN:
        text = f"please indicate which exercise(s) you would like to do on {days[curr_day]}"
        if days[curr_day] == "Mon":
            text = "You have chosen to add a new plan, " + text
        for i, j in available_types.items():
            buttons.append(
                [InlineKeyboardButton(text=i, callback_data=str(j))])
    # Selected exercise
    elif update.callback_query.data in map(chr, range(14, 21)):
        text = "Please indicate another exercise you would like to do."
        val_index = list(available_types.values()).index(
            update.callback_query.data)
        workout = list(available_types.keys())[val_index]
        # if len(final_workouts[days[curr_day]]) != 0 and workout == "Rest":
        #     await update.callback_query.answer("You cannot do that my KING")
        #     # Go back to the ADD_PLAN state and wait for another button press
        #     return ADD_PLAN
        # Add workout to final output
        final_workouts[days[curr_day]].append(workout)
        if update.callback_query.data == REST_DAY:
            return await next_day(update, context)
        # Remove from available types
        available_types.pop(workout)
        available_types.pop("Rest")
        if len(available_types) != 0:
            # No more workout types to add
            for i, j in available_types.items():
                buttons.append(
                    [InlineKeyboardButton(text=i, callback_data=str(j))])
    else:
        logger.error("Not supposed to reach here")
    if curr_day == 6:
        buttons.append([InlineKeyboardButton(
            text="Finish", callback_data=str(FINISH_ADD_PLAN))])
    else:
        buttons.append([InlineKeyboardButton(text="Next day", callback_data=str(
            NEXT_DAY)), InlineKeyboardButton(text="Finish", callback_data=str(FINISH_ADD_PLAN))])
    keyboard = InlineKeyboardMarkup(buttons)

    await update.callback_query.answer()
    await update.callback_query.edit_message_text(text=text, reply_markup=keyboard)
    return ADD_PLAN


async def next_day(update: Update, context: ContextTypes.DEFAULT_TYPE) -> str:
    global final_workouts, workout_types, available_types, days, curr_day
    day = days[curr_day]
    if len(final_workouts[day]) == 0:
        final_workouts[day].append("Rest")
    curr_day += 1
    available_types = workout_types.copy()
    buttons = []
    text = f"please indicate which exercise(s) you would like to do on {days[curr_day]}"
    for i, j in available_types.items():
        buttons.append(
            [InlineKeyboardButton(text=i, callback_data=str(j))])
    if curr_day == 6:
        buttons.append([InlineKeyboardButton(
            text="Finish", callback_data=str(FINISH_ADD_PLAN))])
    else:
        buttons.append([InlineKeyboardButton(text="Next day", callback_data=str(
            NEXT_DAY)), InlineKeyboardButton(text="Finish", callback_data=str(FINISH_ADD_PLAN))])
    keyboard = InlineKeyboardMarkup(buttons)

    await update.callback_query.answer()
    await update.callback_query.edit_message_text(text=text, reply_markup=keyboard)
    return ADD_PLAN


def allMissing(workouts) -> bool:
    res = True
    for i in workouts.values():
        res = res and len(i) == 0
    return res


def fill_in_gaps(workouts):
    for i in workouts.keys():
        if len(workouts[i]) == 0:
            workouts[i].append("Rest")
    return workouts


async def finish_add_plan(update: Update, context: ContextTypes.DEFAULT_TYPE) -> str:
    global final_workouts, workout_types, available_types, curr_day, has_plan
    if allMissing(final_workouts):
        await update.callback_query.answer("Please choose something before finishing")
        return await add_workout(update, context)
    else:
        final_workouts = fill_in_gaps(final_workouts)
    # TODO: Send final workouts to DB
    new_entry = final_workouts.copy()
    new_entry["user_id"] = update.effective_chat.id
    main_plans.insert_one(new_entry)
    available_types = workout_types.copy()
    curr_day = 0
    await update.callback_query.answer("We are done setting your new gym plan! Get ready to bulk KING!")
    return await gym_plan_options(update, context)


edited_day = ""
edited_workout_list = []


async def edit_workout(update: Update, context: ContextTypes.DEFAULT_TYPE) -> str:
    global edited_day, available_types, edited_workout_list
    text = ""
    buttons = []
    if not has_plan:
        logger.error("Should only be visible if plan exists")
        return await gym_plan_options(update, context)
    if update.callback_query.data == FINISH_EDIT_PLAN:
        return EDIT_PLAN
    # Entry point to the edit feature
    if update.callback_query.data == EDIT_PLAN:
        text = "Please choose a day you want to edit"
        for i, j in day_mappings.items():
            buttons.append(
                [InlineKeyboardButton(text=i, callback_data=str(j))])
    # After selecting day
    elif update.callback_query.data in map(chr, range(26, 33)):
        text = "Please choose a new exercise to do"
        val_index = list(day_mappings.values()).index(
            update.callback_query.data)
        edited_day = list(day_mappings.keys())[val_index]
        for i, j in available_types.items():
            buttons.append(
                [InlineKeyboardButton(text=i, callback_data=str(j))])
        pass
    # After selecting workout(s)
    elif update.callback_query.data in map(chr, range(14, 21)):
        text = "Please choose another exercise"
        val_index = list(available_types.values()).index(
            update.callback_query.data)
        workout = list(available_types.keys())[val_index]
        # if len(edited_workout_list) != 0 and workout == "Rest":
        #     await update.callback_query.answer("You cannot do that my KING")
        #     return EDIT_PLAN
        # Add workout to final output
        edited_workout_list.append(workout)
        if update.callback_query.data == REST_DAY:
            return await finish_edit_plan(update, context)
        # Remove from available types
        available_types.pop(workout)
        available_types.pop("Rest")
        if len(available_types) != 0:
            # No more workout types to add
            for i, j in available_types.items():
                buttons.append(
                    [InlineKeyboardButton(text=i, callback_data=str(j))])
        pass
    else:
        pass
    buttons.append([InlineKeyboardButton(
        text="Finish", callback_data=str(FINISH_EDIT_PLAN))])
    keyboard = InlineKeyboardMarkup(buttons)

    await update.callback_query.answer()
    await update.callback_query.edit_message_text(text=text, reply_markup=keyboard)
    return EDIT_PLAN


async def finish_edit_plan(update: Update, context: ContextTypes.DEFAULT_TYPE) -> str:
    global available_types, edited_day, edited_workout_list, workout_types
    available_types = workout_types.copy()
    # User did not change anything
    if edited_day == "" or len(edited_workout_list) == 0:
        await update.callback_query.answer("Please choose something before finishing")
        return await edit_workout(update, context)
    else:
        # TODO: Add to the DB
        main_plans.update_one({"user_id": update.effective_chat.id}, {
                              "$set": {edited_day: edited_workout_list}})
    edited_day = ""
    edited_workout_list = []
    return await gym_plan_options(update, context, True)


async def delete_workout(update: Update, context: ContextTypes.DEFAULT_TYPE) -> str:
    if not has_plan:
        logger.error("This should only be visible if gym plan exists")
        return await gym_plan_options(update, context)
    buttons = []
    buttons.append([InlineKeyboardButton(text="Yes", callback_data=str(
        CONFIRM_REMOVE)), InlineKeyboardButton(text="No", callback_data=str(ABORT_REMOVE))])
    keyboard = InlineKeyboardMarkup(buttons)
    await update.callback_query.edit_message_text(text="Are you sure you want to remove your plan?", reply_markup=keyboard)
    return REMOVE_PLAN


async def confirm_remove(update: Update, context: ContextTypes.DEFAULT_TYPE) -> str:
    global final_workouts, has_plan, displayed_plan
    final_workouts = {
        "Mon": [],
        "Tue": [],
        "Wed": [],
        "Thu": [],
        "Fri": [],
        "Sat": [],
        "Sun": [],
    }
    has_plan = False
    displayed_plan = None
    # TODO: Remove from DB
    main_plans.delete_one({"user_id": update.effective_chat.id})
    temp_plans.delete_one({"user_id": update.effective_chat.id})
    await update.callback_query.answer("Workout removed")
    return await gym_plan_options(update, context)


async def abort_remove(update: Update, context: ContextTypes.DEFAULT_TYPE) -> str:
    await update.callback_query.answer("Aborted removal")
    return await gym_plan_options(update, context)


async def view_recipes(update: Update, context: ContextTypes.DEFAULT_TYPE) -> str:
    pass


async def add_recipe(update: Update, context: ContextTypes.DEFAULT_TYPE) -> str:
    pass


async def delete_recipe(update: Update, context: ContextTypes.DEFAULT_TYPE) -> str:
    pass


async def refresh(update: Update, context: ContextTypes.DEFAULT_TYPE) -> str:
    # Reset the conversation state to SELECT_ACTION
    return await start(update, context)


def main() -> None:
    acquire_lock()
    try:
        application = Application.builder().token(TOKEN).build()

        # In charge of handling different options selected
        other_gym_plans = [
            CallbackQueryHandler(clock_workout, pattern="^" +
                                 str(CLOCK_WORKOUT) + "$"),
            CallbackQueryHandler(
                add_workout, pattern="^" + str(ADD_PLAN) + "$"),
            CallbackQueryHandler(
                edit_workout, pattern="^" + str(EDIT_PLAN) + "$"),
            CallbackQueryHandler(
                delete_workout, pattern="^" + str(REMOVE_PLAN) + "$")
        ]

        other_recipes = [CallbackQueryHandler(
            add_recipe, pattern="^" + str(ADD_RECIPE) + "$"),
            CallbackQueryHandler(
            delete_recipe, pattern="^" + str(DELETE_RECIPE) + "$")]

        # In charge of bringing the conversation to the SELECT_GYM_PLAN_ACTION state
        # next states: CREATE_NEW_PLAN, EDIT_PLAN, DELETE_PLAN
        gym_plan_handler = ConversationHandler(
            entry_points=[CallbackQueryHandler(
                gym_plan_options, pattern="^" + str(SELECT_GYM_PLAN_ACTION) + "$")],
            states={
                SELECT_GYM_PLAN_ACTION:  # After all operations are done, should go back to this state
                other_gym_plans,
                ADD_PLAN: [CallbackQueryHandler(
                    add_workout, pattern=f"^{BACK}$|^{ARMS}$|^{LEGS}$|^{ABS}$|^{CHEST}$|^{SHOULDERS}$|^{REST_DAY}$"), CallbackQueryHandler(finish_add_plan, pattern="^" + str(FINISH_ADD_PLAN) + "$"), CallbackQueryHandler(next_day, pattern="^" + str(NEXT_DAY) + "$")],
                EDIT_PLAN: [CallbackQueryHandler(
                    edit_workout, pattern=f"^{MON}$|^{TUES}$|^{WED}$|^{THURS}$|^{FRI}$|^{SAT}$|^{SUN}$|^{BACK}$|^{ARMS}$|^{LEGS}$|^{ABS}$|^{CHEST}$|^{SHOULDERS}$|^{REST_DAY}$"), CallbackQueryHandler(finish_edit_plan, pattern="^" + str(FINISH_EDIT_PLAN) + "$")],
                REMOVE_PLAN: [CallbackQueryHandler(confirm_remove, pattern="^" + str(
                    CONFIRM_REMOVE) + "$"), CallbackQueryHandler(abort_remove, pattern="^" + str(ABORT_REMOVE) + "$")],
                CLOCK_WORKOUT: [CallbackQueryHandler(
                    clock_workout, pattern=f"^{COMPLETED_WORKOUT}$|^{ALT_WORKOUT}$|^{INCOMPLETE_WORKOUT}$|^{BACK}$|^{ARMS}$|^{LEGS}$|^{ABS}$|^{CHEST}$|^{SHOULDERS}$|^{REST_DAY}$"), CallbackQueryHandler(finish_clock_workout, pattern="^" + FINISH_EDIT_PLAN + "$")]

            },
            fallbacks=[CommandHandler("refresh", refresh_nested)], map_to_parent={
                REFRESH: REFRESH
            }
        )

        # In charge of bringing the conversation to the SELECT_RECIPE_ACTION state
        # next states: ADD_RECIPE, DELETE_RECIPE
        recipe_handler = ConversationHandler(
            entry_points=[CallbackQueryHandler(recipe_options, pattern="^" + str(SELECT_RECIPE_ACTION) + "$")], states={
                SELECT_RECIPE_ACTION: other_recipes
            }, fallbacks=[CommandHandler("refresh", refresh_nested)], map_to_parent={
                REFRESH: REFRESH
            }
        )

        # Top level handlers
        selection_handlers = [
            gym_plan_handler,
            recipe_handler,
        ]

        # Main entry point
        conv_handler = ConversationHandler(entry_points=[CommandHandler("start", start)], states={
            SELECT_ACTION: selection_handlers,
            # Call refresh twice to work???
            REFRESH: [CommandHandler("continue", start)]
        }, fallbacks=[CommandHandler("stop", stop), CommandHandler("help", helper), CommandHandler("refresh", refresh)])

        application.add_handler(conv_handler)

        application.run_polling(allowed_updates=Update.ALL_TYPES)
    except KeyboardInterrupt:
        print("Keyboard interrupt received. Exiting.")

    finally:
        # Release the lock when the bot finishes
        release_lock()


if __name__ == "__main__":
    db = cluster[DATABASE_NAME]
    main_plans = db[COLLECTION_NAME_MAIN]
    temp_plans = db[COLLECTION_NAME_SEC]
    main()
