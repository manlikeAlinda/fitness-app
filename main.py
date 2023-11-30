import json
import os
import sqlite3 # Import the sqlite3 module
from kivy.lang import Builder
from kivy.app import App
from kivy.clock import Clock, mainthread
from kivy.properties import NumericProperty
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.screenmanager import ScreenManager, Screen
from kivymd.app import MDApp
from plyer import uniqueid
from kivy.utils import platform
from kivy.core.window import Window

# Set the window size for a mobile device simulation
Window.size = (360, 600)

# Android-specific imports and initializations
if platform == 'android':
    from jnius import autoclass, PythonJavaClass, java_method
    PythonActivity = autoclass('org.kivy.android.PythonActivity')
    SensorManager = autoclass('android.hardware.SensorManager')
    Sensor = autoclass('android.hardware.Sensor')
    SensorEventListener = PythonJavaClass('__javainterfaces__', ['android/hardware/SensorEventListener'])
else:
    PythonActivity = SensorManager = Sensor = SensorEventListener = None


# Load all KV files at once
kv_files = ['signup.kv', 'login.kv', 'dashboard.kv', 'heart_rate.kv', 'start_training.kv', 'steps_counter.kv']
for kv in kv_files:
    Builder.load_file(kv)


class SignupScreen(BoxLayout):

    def __init__(self, **kwargs):
        super(SignupScreen, self).__init__(**kwargs)
        self.db_name = 'users.db'
        self.init_database()

    def init_database(self):
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL UNIQUE,
                email TEXT NOT NULL UNIQUE,
                password TEXT NOT NULL,
                session TEXT DEFAULT 'inactive'
            )
        ''')
        conn.commit()
        conn.close()

    def save_data(self):
        username = self.ids.username_input.text
        email = self.ids.email_input.text
        password = self.ids.password_input.text  # Consider hashing the password before storage

        # Check if the data already exists
        if not self.data_exists(username, email):
            conn = sqlite3.connect(self.db_name)
            cursor = conn.cursor()
            try:
                cursor.execute('INSERT INTO users (username, email, password) VALUES (?, ?, ?)',
                               (username, email, password))
                conn.commit()
                self.ids['success_label'].text = 'Account created successfully!'
            except sqlite3.IntegrityError:
                self.ids.username_input.text = 'Username or Email already exists!'
            finally:
                conn.close()
            Clock.schedule_once(self.redirect_to_login, 3)
        else:
            self.ids.username_input.text = 'Username or Email already exists!'

    def data_exists(self, username, email):
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        cursor.execute('SELECT id FROM users WHERE username = ? OR email = ?', (username, email))
        exists = cursor.fetchone() is not None
        conn.close()
        return exists
    
    def redirect_to_login(self, *args):
        app = App.get_running_app()
        app.root.current = 'login'


    def hex_to_rgba(value):
        value = value.lstrip('#')
        lv = len(value)
        return tuple(int(value[i:i + lv // 3], 16) / 255.0 for i in range(0, lv, lv // 3)) + (1,)


class LoginScreen(Screen):

    def login(self):
        username = self.ids.username_input.text
        password = self.ids.password_input.text  # You should verify the hashed version if you hash passwords

        conn = sqlite3.connect('users.db')
        cursor = conn.cursor()
        cursor.execute('SELECT id, username, email, session FROM users WHERE username = ? AND password = ?', (username, password))
        user = cursor.fetchone()
        conn.close()

        if user:
            # The user tuple consists of (id, username, email, session)
            user_id, username, email, session = user
            if session == 'active':
                self.ids['login_status'].text = 'User already logged in!'
            else:
                self.set_user_active(user_id)
                self.ids['login_status'].text = 'Login successful!'
                # Update current_user
                app = MDApp.get_running_app()
                app.current_user = {'id': user_id, 'username': username, 'email': email, 'session': 'active'}
                # Redirect to dashboard
                self.redirect_to_dashboard()
        else:
            self.ids['login_status'].text = 'Invalid credentials or user not found. Sign up first!'

    def set_user_active(self, user_id):
        conn = sqlite3.connect('users.db')
        cursor = conn.cursor()
        cursor.execute('UPDATE users SET session = "active" WHERE id = ?', (user_id,))
        conn.commit()
        conn.close()

    def redirect_to_dashboard(self):
        app = MDApp.get_running_app()
        app.root.current = 'dashboard'
        # Optionally, update dashboard data here if necessary
        dashboard_screen = app.root.get_screen('dashboard')
        if dashboard_screen:
            dashboard_screen.on_enter()




class DashboardScreen(Screen):
    def on_enter(self):
        super().on_enter()  # Call the super class method if it exists
        self.update_user_info()

    def update_user_info(self):
        app = MDApp.get_running_app()
        self.ids.username.text = f"Hi, {app.current_user['username']}" if app.current_user else "Hi, guest"
        self.ids.email.text = f"Email: {app.current_user['email']}" if app.current_user else "Email: "

    def logout(self):
        app = MDApp.get_running_app()
        if app.current_user:
            conn = sqlite3.connect('users.db')
            cursor = conn.cursor()
            cursor.execute('UPDATE users SET session = "inactive" WHERE id = ?', (app.current_user['id'],))
            conn.commit()
            conn.close()

            # Clear the current user data
            app.current_user = None

            # Redirect to the login screen
            app.root.current = 'login'

# Define the HeartRateScreen class
if platform == 'android':
    class SensorListener(PythonJavaClass):
        __javainterfaces__ = ['android/hardware/SensorEventListener']

        def __init__(self, callback):
            super().__init__()
            self.callback = callback

        @java_method('(Landroid/hardware/Sensor;I)V')
        def onAccuracyChanged(self, sensor, accuracy):
            pass

        @java_method('(Landroid/hardware/SensorEvent;)V')
        def onSensorChanged(self, event):
            if hasattr(self.callback, 'update_heart_rate'):
                heart_rate = event.values[0]
                self.callback.update_heart_rate(heart_rate)
            elif hasattr(self.callback, 'update_steps'):
                step_count = event.values[0]
                self.callback.update_steps(step_count)


class HeartRateScreen(Screen):
    heart_rate = NumericProperty(0)

    def __init__(self, **kwargs):
        super(HeartRateScreen, self).__init__(**kwargs)
        if platform == 'android':
            self.activity = PythonActivity.mActivity
            self.sensor_manager = self.activity.getSystemService(SensorManager.SENSOR_SERVICE)
            self.sensor = self.sensor_manager.getDefaultSensor(Sensor.TYPE_HEART_RATE)
            self.sensor_listener = SensorListener(self)

    def on_enter(self):
        if platform == 'android':
            self.sensor_manager.registerListener(
                self.sensor_listener,
                self.sensor,
                SensorManager.SENSOR_DELAY_NORMAL
            )

    def on_leave(self):
        if platform == 'android':
            self.sensor_manager.unregisterListener(self.sensor_listener)

    @mainthread
    def update_heart_rate(self, heart_rate):
        self.heart_rate = heart_rate
        self.ids.heart_rate_display.text = f'Heart Rate: {self.heart_rate} BPM'


class TrainingScreen(Screen):
    timer_event = None  # Class variable to hold the scheduled event for reference
    total_seconds = 0  # Class variable to keep track of the time elapsed

    def update_timer(self, dt):
        # This method will be called every second to update the timer
        self.total_seconds += 1
        minutes, seconds = divmod(self.total_seconds, 60)
        hours, minutes = divmod(minutes, 60)
        # Update timer label
        self.ids.timer_label.text = f'{hours:02d}:{minutes:02d}:{seconds:02d}'

    def start_training(self):
        # Start the timer by scheduling update_timer to be called every second
        if not self.timer_event:  # Prevent multiple schedules if already running
            self.timer_event = Clock.schedule_interval(self.update_timer, 1)

    def stop_training(self):
        # Stop the timer by unscheduling the event
        if self.timer_event:
            Clock.unschedule(self.timer_event)
            self.timer_event = None

    def reset_training(self):
        # Reset the timer and stop if it's running
        self.stop_training()  # Stop the current timer
        self.total_seconds = 0  # Reset the counter
        # Reset the timer label to '00:00:00'
        self.ids.timer_label.text = '00:00:00'


class StepsCounterScreen(Screen):
    steps = NumericProperty(0)

    def __init__(self, **kwargs):
        super(StepsCounterScreen, self).__init__(**kwargs)
        if platform == 'android':
            from jnius import autoclass
            PythonActivity = autoclass('org.kivy.android.PythonActivity')
            SensorManager = autoclass('android.hardware.SensorManager')
            Sensor = autoclass('android.hardware.Sensor')
            self.sensor_manager = PythonActivity.mActivity.getSystemService(SensorManager.SENSOR_SERVICE)
            self.step_sensor = self.sensor_manager.getDefaultSensor(Sensor.TYPE_STEP_COUNTER)
            self.sensor_listener = SensorListener(self)
        else:
            self.sensor_manager = None
            self.step_sensor = None
            self.sensor_listener = None

    def on_enter(self):
        # Start listening for step updates when the screen is entered
        self.sensor_manager.registerListener(self.sensor_listener, self.step_sensor, SensorManager.SENSOR_DELAY_UI)

    def on_leave(self):
        # Stop listening for step updates when the screen is left
        self.sensor_manager.unregisterListener(self.sensor_listener)

    def update_steps(self, step_count):
        self.steps = step_count

class UserFormApp(MDApp):
    current_user = None  # Class variable to hold the current user

    def build(self):
        self.theme_cls.material_style = "M3"
        self.theme_cls.theme_style = "Dark"
        sm = ScreenManager()

        # Create instances of the screens and add them to the ScreenManager
        signup_screen = Screen(name='signup')
        signup_screen.add_widget(SignupScreen())

        login_screen = Screen(name='login')
        login_screen.add_widget(LoginScreen())

        dashboard_screen = Screen(name='dashboard')
        dashboard_screen.add_widget(DashboardScreen())

        heart_rate_screen = Screen(name='heart_rate')
        heart_rate_screen.add_widget(HeartRateScreen())

        training_screen = Screen(name='training')
        training_screen.add_widget(TrainingScreen())

        steps_counter_screen = Screen(name='steps_counter')
        steps_counter_screen.add_widget(StepsCounterScreen())

        # Add screens to the ScreenManager
        sm.add_widget(signup_screen)
        sm.add_widget(login_screen)
        sm.add_widget(dashboard_screen)
        sm.add_widget(heart_rate_screen)
        sm.add_widget(training_screen)
        sm.add_widget(steps_counter_screen)

        return sm
    
    def on_start(self):
        self.current_user = None  # Make sure to reset current_user on app start

if __name__ == '__main__':
    UserFormApp().run()
