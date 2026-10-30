import os
import numpy as np
import pandas as pd
import os
import torch
from torch.utils.data import Dataset, DataLoader
from sklearn.preprocessing import StandardScaler

from torch.utils.data import random_split, DataLoader
import warnings
from pathlib import Path
import sys
import logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
_PATH_LOGGED = False

# Ensure local utils/ is imported before any similarly-named packages on PYTHONPATH.
_project_root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_project_root))

from utils.timefeatures import time_features
from utils.tools import convert_tsf_to_dataframe

warnings.filterwarnings('ignore')


def preprocess_nasa_data(file_path, target_column='WS50M'):
    import pandas as pd
    import numpy as np

    # 1) Find the first data/header line after "-END HEADER-"
    with open(file_path, 'r', errors='ignore') as f:
        lines = f.readlines()

    data_start_idx = None
    for i, line in enumerate(lines):
        if '-END HEADER-' in line:
            data_start_idx = i + 1  # header row is the very next line
            break
    if data_start_idx is None:
        raise ValueError("'-END HEADER-' not found in file.")

    # 2) Read with a robust delimiter & engine
    #    - Handle tabs or any whitespace, or commas
    #    - Use python engine for regex sep
    #    - Try UTF-8 first; if it fails, try UTF-16 (some NASA files are UTF-16)
    try:
        df_raw = pd.read_csv(
            file_path,
            skiprows=data_start_idx,
            sep=r'[,\t\s]+',
            engine='python'
        )
    except UnicodeError:
        df_raw = pd.read_csv(
            file_path,
            skiprows=data_start_idx,
            sep=r'[,\t\s]+',
            engine='python',
            encoding='utf-16'
        )

    # 3) Normalize column names, strip BOM if any
    df_raw.columns = [c.strip().upper().replace('\ufeff', '') for c in df_raw.columns]

    # 4) Ensure expected time parts exist
    required = ['YEAR', 'MO', 'DY', 'HR']
    if not all(col in df_raw.columns for col in required):
        raise KeyError(
            f"Expected time columns {required} not found. "
            f"Got: {sorted(df_raw.columns)}"
        )

    # 5) Build datetime column
    df_raw['date'] = pd.to_datetime(
        df_raw[['YEAR', 'MO', 'DY', 'HR']].rename(columns={'MO': 'MONTH', 'DY': 'DAY', 'HR': 'HOUR'})
    )

    # 6) Drop the separate time columns
    df_raw = df_raw.drop(columns=required)

    # 7) Clean fill values, interpolate numeric columns
    df_raw = df_raw.replace(-999, np.nan)
    num_cols = df_raw.select_dtypes(include=[np.number]).columns
    if len(num_cols) > 0:
        df_raw[num_cols] = df_raw[num_cols].interpolate(method='linear', limit_direction='both')

    # 8) Put 'date' first
    df_raw = df_raw[['date'] + [c for c in df_raw.columns if c != 'date']]

    # 9) Optional: confirm target exists (WS50M in your screenshot)
    if target_column.upper() not in df_raw.columns:
        raise KeyError(f"Target '{target_column}' not found. Available: {sorted(df_raw.columns)}")

    return df_raw


def get_chunked_dataset(files_to_process, chunk_size):
    """
    Reads multiple CSVs, breaks each into chunks of a specified size,
    and combines all chunks into a single new file.
    """
    logging.info("--- Starting Chunk Extraction and Combination Script ---")
    logging.info(f"Chunk size set to: {chunk_size} rows\n")

    # This list will hold all the small DataFrame chunks from all files
    all_chunks = []

    # --- Process Files ---
    # files_to_process = [file1, file2]

    # Check for column consistency before processing
    num_chunks = 99999999
    for i in range(len(files_to_process)):
        files_to_process[i] = preprocess_nasa_data(files_to_process[i])
        num_chunks = min(num_chunks, len(files_to_process[i]) // chunk_size)
        if num_chunks == 0:
            logging.info(f"   -> Not enough data for even one chunk. Skipping.")

    # Loop through and extract each chunk
    for i in range(num_chunks):
        for file in files_to_process:
            start_index = i * chunk_size
            end_index = start_index + chunk_size
            chunk = file.iloc[start_index:end_index]
            all_chunks.append(chunk)

    # --- Step 3: Combine all collected chunks and save ---
    if not all_chunks:
        logging.info("\n❌ No chunks were extracted from any file. No output file will be created.")
        return

    logging.info(f"\n--- Combining all {len(all_chunks)} extracted chunks... ---")

    # 'ignore_index=True' creates a new clean index for the combined file
    combined_df = pd.concat(all_chunks, ignore_index=True)

    # Save to a new CSV without the pandas index column
    return combined_df

class Dataset_Custom(Dataset):
    def __init__(self, root_path, flag='train', size=None,
                 features='S', data_path='001.csv',
                 target='speed', scale=True, timeenc=0, freq='h',
                 percent=10, max_len=-1, train_all=False, dataset_name="none"):
        # size [seq_len, label_len, pred_len]
        # info
        data_path = data_path[0] if isinstance(data_path, list) else data_path
        logging.info("Dataset_Custom: dataset_name = {}".format(dataset_name))
        logging.info("Dataset_Custom: data_path = {}".format(data_path))
        if size == None:
            self.seq_len = 24 * 4 * 4
            self.label_len = 24 * 4
            self.pred_len = 24 * 4
        else:
            self.seq_len = size[0]
            self.label_len = size[1]
            self.pred_len = size[2]
        if dataset_name == "none":
            self.dataset_name = Path(data_path).stem.lower()
        else:
            self.dataset_name = str(dataset_name).lower()
        # init
        assert flag in ['train', 'test', 'val']
        type_map = {'train': 0, 'val': 1, 'test': 2}
        self.set_type = type_map[flag]

        self.features = features
        self.target = target
        self.scale = scale
        self.timeenc = timeenc
        self.freq = freq
        self.percent = percent

        self.root_path = root_path
        self.data_path = data_path
        self.__read_data__()

        self.enc_in = self.data_x.shape[-1]
        self.tot_len = len(self.data_x) - self.seq_len - self.pred_len + 1

    def __read_data__(self):
        self.scaler = StandardScaler()

        if 'nasa' in self.dataset_name or any(x in self.data_path.lower() for x in ['kokshetau', 'aktobe']):
            df_raw = preprocess_nasa_data(os.path.join(self.root_path, self.data_path), self.target)
        else:
            df_raw = pd.read_csv(os.path.join(self.root_path,
                                              self.data_path))
            if 'date' not in df_raw.columns:
                normalized_map = {}
                for col in df_raw.columns:
                    norm = (
                        str(col)
                        .strip()
                        .lower()
                        .replace(" ", "")
                        .replace("_", "")
                        .replace("-", "")
                        .replace("/", "")
                        .replace("\\", "")
                    )
                    normalized_map[col] = norm
                date_candidates = [
                    col for col, norm in normalized_map.items()
                    if norm in {"date", "datetime", "timestamp"}
                ]
                if date_candidates:
                    df_raw = df_raw.rename(columns={date_candidates[0]: "date"})
            if 'date' not in df_raw.columns:
                raise KeyError(f"'date' column not found in {self.data_path}. Available columns: {list(df_raw.columns)}")
            if self.target not in df_raw.columns:
                raise KeyError(f"Target '{self.target}' not found in {self.data_path}. Available columns: {list(df_raw.columns)}")

            # Ensure a valid chronological datetime axis for time feature extraction/splitting.
            df_raw['date'] = pd.to_datetime(df_raw['date'], errors='raise')
            if not df_raw['date'].is_monotonic_increasing:
                df_raw = df_raw.sort_values('date').reset_index(drop=True)

            # Drop rows where target is NaN to prevent StandardScaler from producing NaN mean/std.
            n_before = len(df_raw)
            df_raw = df_raw.dropna(subset=[self.target]).reset_index(drop=True)
            n_dropped = n_before - len(df_raw)
            if n_dropped > 0:
                logging.warning(f"Dropped {n_dropped} rows with NaN target '{self.target}' from {self.data_path}")

        '''
        df_raw.columns: ['date', ...(other features), target feature]
        '''
        cols = list(df_raw.columns)
        cols.remove(self.target)
        cols.remove('date')
        df_raw = df_raw[['date'] + cols + [self.target]]
        # logging.info(cols)
        num_train = int(len(df_raw) * 0.7)
        num_test = int(len(df_raw) * 0.2)
        num_vali = len(df_raw) - num_train - num_test
        border1s = [0, num_train - self.seq_len, len(df_raw) - num_test - self.seq_len]
        border2s = [num_train, num_train + num_vali, len(df_raw)]
        border1 = border1s[self.set_type]
        border2 = border2s[self.set_type]

        if self.set_type == 0:
            border2 = (border2 - self.seq_len) * self.percent // 100 + self.seq_len

        if self.features == 'M' or self.features == 'MS':
            cols_data = df_raw.columns[1:]
            df_data = df_raw[cols_data]
        elif self.features == 'S':
            df_data = df_raw[[self.target]]

        if self.scale:
            train_data = df_data[border1s[0]:border2s[0]]
            self.scaler.fit(train_data.values)
            data = self.scaler.transform(df_data.values)
        else:
            data = df_data.values

        df_stamp = df_raw[['date']][border1:border2]
        df_stamp['date'] = pd.to_datetime(df_stamp.date)
        if self.timeenc == 0:
            df_stamp['month'] = df_stamp.date.apply(lambda row: row.month, 1)
            df_stamp['day'] = df_stamp.date.apply(lambda row: row.day, 1)
            df_stamp['weekday'] = df_stamp.date.apply(lambda row: row.weekday(), 1)
            df_stamp['hour'] = df_stamp.date.apply(lambda row: row.hour, 1)
            data_stamp = df_stamp.drop(['date'], axis=1).values

        elif self.timeenc == 1:
            data_stamp = time_features(pd.to_datetime(df_stamp['date'].values), freq=self.freq)
            data_stamp = data_stamp.transpose(1, 0)

        self.data_x = data[border1:border2]
        self.data_y = data[border1:border2]
        self.data_stamp = data_stamp

    def __getitem__(self, index):
        feat_id = index // self.tot_len
        s_begin = index % self.tot_len

        s_end = s_begin + self.seq_len
        r_begin = s_end - self.label_len
        r_end = r_begin + self.label_len + self.pred_len
        seq_x = self.data_x[s_begin:s_end, feat_id:feat_id + 1]
        seq_y = self.data_y[r_begin:r_end, feat_id:feat_id + 1]
        seq_x_mark = self.data_stamp[s_begin:s_end]
        seq_y_mark = self.data_stamp[r_begin:r_end]

        return seq_x, seq_y, seq_x_mark, seq_y_mark

    def __len__(self):
        return (len(self.data_x) - self.seq_len - self.pred_len + 1) * self.enc_in

    def inverse_transform(self, data):
        return self.scaler.inverse_transform(data)
