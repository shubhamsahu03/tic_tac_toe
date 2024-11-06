class Config:
    SECRET_KEY = 'my_super_secret_key_that_is_long_and_random_123456'

    # MySQL configurations for a single database
    MYSQL_HOST = 'localhost'
    MYSQL_USER = 'root'
    MYSQL_PASSWORD = '4790'
    MYSQL_DB = 'game_db'  # Single database for both authentication and stats
