export const CUSTOMER_SESSION_KEY = 'lead_magnet_customer_session';
export const CUSTOMER_USERS_KEY = 'lead_magnet_customer_users';
export const ADMIN_SESSION_KEY = 'lead_magnet_admin_session';

export function readStorage(key, fallbackValue = null) {
  try {
    const item = localStorage.getItem(key);
    return item ? JSON.parse(item) : fallbackValue;
  } catch (error) {
    console.error(`Error reading ${key} from storage:`, error);
    return fallbackValue;
  }
}

export function writeStorage(key, value) {
  try {
    localStorage.setItem(key, JSON.stringify(value));
  } catch (error) {
    console.error(`Error writing ${key} to storage:`, error);
  }
}

export function removeStorage(key) {
  try {
    localStorage.removeItem(key);
  } catch (error) {
    console.error(`Error removing ${key} from storage:`, error);
  }
}
