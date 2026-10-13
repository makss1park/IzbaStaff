from aiogram.fsm.state import State, StatesGroup

class EditEmployeeState(StatesGroup):
    waiting_full_name = State()
    waiting_phone = State()
    waiting_rate = State()
    waiting_schedule = State()
    waiting_role = State()

class QuickReportState(StatesGroup):
    waiting_text = State()
    waiting_photo = State()




class AdminShiftEditState(StatesGroup):
    waiting_minutes = State()


class AdminFineState(StatesGroup):
    waiting_reason = State()
    waiting_amount = State()



class AdminSettingsState(StatesGroup):
    waiting_reports_days = State()


class AdminReportRecipientsState(StatesGroup):
    selecting_users = State()


class CatalogCreateState(StatesGroup):
    waiting_title = State()
    waiting_tags = State()
    waiting_photos = State()


class CatalogSearchState(StatesGroup):
    waiting_query = State()
