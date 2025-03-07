import numpy as np
import xarray as xr
import pandas as pd
import copy
import time
import glob
from datetime import datetime, timedelta
import config

def catch(user_input, defined_type):  
    """ Function that check type.
        Can be used in list comprehension"""
    if isinstance(user_input, defined_type):
        pass
    else:
        raise TypeError(f" Input value '{user_input}'"
                        f" must be a {defined_type}")

class ModelInputError(Exception):
    """ Custom model input error"""
    pass

class ModelOutput:
    """ A Python object used to read an format various atmospheric
        model output types"""
    
    def __init__(self, model_name, data_format, main_dir, sub_dir, 
                valid_time, domain = "d01"):
        """ Sets model attributes from user input
        
            Parameters
            ----------
            model_name : str
                The model name, supported values are `wrf`,
                `rrfs`, and `hrrr`
                
            data_format : str
                The model data type, supported values are 
                `netcdf` and `grib2`
                
            main_dir : str
                The main model output directory
                
            sub_dir : str
                Subdirectories to be searched for model output.
                Can be a partial string, `**` will be appended
                
            valid_time : str
                Model output valid time
                
            domain : str
                domain to read, default is `d01` for wrf, 
                unused for `rrfs` and `hrrr`
        """
        input_params = {"model_name": model_name,
                        "data_format": data_format,
                        "main_dir": main_dir,
                        "sub_dir": sub_dir,
                        "valid_time": valid_time,
                        "domain": domain
                        }

        [catch(i, str) for i in input_params.values()]        
        input_params = {k:v.strip().lower() for k, v in input_params.items()}

        # Check for supported models listed in config.py
        tmpkey = "model_name"
        if input_params[tmpkey] in config.supported_models:
            setattr(self, tmpkey, input_params[tmpkey])
        else:
            raise ModelInputError(f"Model name {input_params[tmpkey]}"
                            f" is not supported. List of supported model"
                            f" names: {[config.supported_models]}")

        # Check for supported data formats
        tmpkey = "data_format"
        if input_params[tmpkey] in config.supported_formats:
            setattr(self, tmpkey, input_params[tmpkey])
        else:
            raise ModelInputError(f"Data format {input_params[tmpkey]}"
                            f" is not supported. List of supported data"
                            f" formats: {[config.supported_formats]}")

        tmpkey = "main_dir"
        tmpval = input_params[tmpkey]
        tmpval = tmpval+"/" if not tmpval.endswith("/") else tmpval
        setattr(self, tmpkey, tmpval)   

        tmpkey = "sub_dir"
        tmpval = input_params[tmpkey]
        tmpval = tmpval+"**/" if not tmpval.endswith("**/") else tmpval
        setattr(self, tmpkey, tmpval)   

        tmpkey = "valid_time"
        tmpval = input_params[tmpkey]
        setattr(self, tmpkey, tmpval)    
         
        tmpkey = "domain"
        tmpval = input_params[tmpkey]
        setattr(self, tmpkey, tmpval)   
        
        setattr(self,"input_keys",input_params.keys())
        print(self)
        
    def __repr__(self):        
        """ Returns a string of all users specified model attributes"""
        output_string = [i+": "+getattr(self,i) for i in self.input_keys]
        return f"User variables have been set:\n"+"\n".join(output_string)
    
    def find_valid_files(self):
        """Finds one or more valid files from user input of
            main_dir, sub_dir, and valid_time"""
        
        # Model specific file search
        if(self.model_name == "wrf"):
            search_path = self.main_dir+self.sub_dir+"wrfout_"+self.domain+"*"
        elif(self.model_name == "wrf-geogrid"):
            search_path = self.main_dir+"geo_em."+self.domain+".nc"
        elif(self.model_name == "rrfs"):
            search_path = self.main_dir+self.sub_dir+"dyn"+"*"
        elif(self.model_name == "hrrr"):
            search_path = self.main_dir+self.sub_dir+"*"
        else:
            search_path = self.main_dir+self.sub_dir+"*"
            
        # File search path
        file_search = glob.glob(search_path)

        # Geogrid does not have time associated with it
        if self.model_name == "wrf-geogrid":
            # If no files found search subdirectories
            if not file_search:
                search_path = self.main_dir+self.sub_dir \
                              +"geo_em."+self.domain+".nc"
                file_search = glob.glob(search_path)
                if len(file_search) == 1:
                   print(f"Single geogrid file found in subdirectory: "
                         f"{file_search[0]}")
                   setattr(self, "valid_files", [file_search[0]])
                   setattr(self, "unread_files", [file_search[0]])
                   return
                else:
                   raise ModelInputError(f"Multiple geogrid files found: "
                                         f"{file_search}")
            else:
                if len(file_search) == 1:
                   print(f"Single geogrid file found in main directory: "
                         f"{file_search[0]}")
                   setattr(self, "valid_files", [file_search[0]])
                   setattr(self, "unread_files", [file_search[0]])
                   return
                else:
                   raise ModelInputError(f"Multiple geogrid files found: "
                                         f"{file_search}")

        # Unix time
        valid_time_unix = datetime.strptime(self.valid_time,
                                        config.time_format[self.model_name]
                                        ).timestamp()

        # The starting index of year, %Y, in format string
        year_index_start = config.time_format[self.model_name].index("%Y")

        #.. valid_file will not match if file format is
        #.. yyyymmdd/fcast_001 and if yyymmdd is not valid_time
        #.. Must find base time + forecast hour (done below)
        valid_file = [f for f in file_search if self.valid_time in f]
        
        # Sorted list of all files that include the correct year: 'YYYY'
        all_files_matching_year = sorted(list(set(
            [f for f in file_search \
                if self.valid_time[year_index_start:4] in f])))
        
        # Error if nothing in all_files_matching_year
        if not all_files_matching_year:
            raise ModelInputError(f"File search returned "
                                  f"no matches. Check values of "
                                  f"'main_dir' = {self.main_dir}, \n" 
                                  f"'sub_dir' = {self.sub_dir}, and "
                                  f"'valid_time' = {self.valid_time}")
            
        # Base time, based on all matching files
        base_time_file = all_files_matching_year[0]
        
        time_index_start = base_time_file.rfind(
            self.valid_time[year_index_start:4])
        base_time = base_time_file[
            time_index_start:time_index_start+len(self.valid_time)]
        base_time_dtformat = datetime.strptime(
            base_time, config.time_format[self.model_name]) 

        file_format = ["".join(f[time_index_start:].split(base_time+"/")) \
                       for f in all_files_matching_year]
        
        # Strip off the ending if there is one
        file_format = [f[:-3] if f.endswith(".nc") \
                       else f for f in file_format]
        file_format = [f[:-4] if f.endswith(".ncf") \
                       else f for f in file_format]
        file_format = [f[:-5] if f.endswith(".grib") \
                       else f for f in file_format]
        file_format = [f[:-6] if f.endswith(".grib2") \
                       else f for f in file_format]
        
        # Get forecast and init hour for file format: hrrr.t00z.wrfnatf06.nc
        # or yyyymmddhh/f006.nc, these lists are empty otherwise 
        forecast_hours = [i[i.rfind("f")+1::] \
                          for i in file_format if i.rfind("f")>0]
            
        #.. Initialization hour is alway format '\d\d', '2' is hardcoded
        init_hours = [i[i.rfind("z")-2:i.rfind("z")] \
                      for i in file_format if i.rfind("z")>0]

        valid_time_dtformat = datetime.strptime(
            self.valid_time, config.time_format[self.model_name])
        
        valid_minus_base_seconds = (valid_time_dtformat \
            - base_time_dtformat).total_seconds()
        
        if valid_file:
            if len(valid_file) == 1:
                # If one valid file is found
                print(f"Base time is {base_time}, forecast length of "
                      f"valid time is {valid_minus_base_seconds} s")
                print(f"Single valid file found: {valid_file[0]}")
                setattr(self, "valid_files", valid_file)
                setattr(self, "unread_files", valid_file)
                print(f"New attributes 'valid_files' and 'unread_files' set")
            else:
                # Multiple valid files
                multiple_valid_files = [x for _,x in sorted(
                    zip(forecast_hours, all_files_matching_year))]
                print(f"Multple valid files found: ")
                new_valid_files = [f for f in multiple_valid_files \
                                    if self.valid_time in f]
                # Assumed that if init_hour is found, multiple
                # forecasts valid at the same time are in directory.
                # Else, assume that multiple files were matched because
                # an analysis time was chosen, matching the file directory
                if init_hours:
                    print(f"Various initialized times found.")
                    [print(f"{f}") for f in new_valid_files]
                    setattr(self, "valid_files", new_valid_files)
                    setattr(self, "unread_files", new_valid_files)
                    print(f"New attributes "
                          f"'valid_files' and 'unread_files' set")
                else:
                    # For yyyymmddhh/forecast01, if valid_time is set to
                    # the analysis, then all forecast files in yyyymmddhh
                    # will be matched. This takes the first file in the 
                    # sorted listed, or the anlaysis. If the valid time is 
                    # the next hour, then valid_time will be different than
                    # the search directory and no valid times will match
                    # and the valid file will be found in the else below
                    print(f"Single analysis file found: {new_valid_files[0]}")
                    setattr(self, "valid_files", [new_valid_files[0]])
                    setattr(self, "unread_files", [new_valid_files[0]])
                    print(f"New attributes "
                          f"'valid_files' and 'unread_files' set")
        else:
            # No valid file found, assume that the formatting is
            # basetime/forecast
            print(f"No exact file matches found...")
            print(f"    valid files assumed to have format: "
                  f"'base_time/fcast', or yyyymmddhh/f006,\n"
                  f"    where yyyymmddhh != valid_time.")
            valid_hour_int = int(valid_minus_base_seconds/3600.)
            time_match = [int(i)==valid_hour_int for i in forecast_hours]
            if not any(time_match):
                raise ModelInputError(f"No valid forecasts were found in "
                                      f"{search_path} \n"
                                      f"Check 'valid_time' = "
                                      f"{self.valid_time}")
            time_match_index = time_match.index(True)
            forecast_length = "f"+forecast_hours[time_match_index]
            print(f"Valid time is {self.valid_time} =")
            print(f"    base time + forecast length: "
                  f"{base_time} + {forecast_length}")
            new_file_search = base_time_file[
                0:base_time_file.rfind("f")]+forecast_length
            new_valid_file = glob.glob(new_file_search+"*")
            if new_valid_file:
                print(f"Base time is {base_time}, forecast length of "
                      f"valid time is {valid_minus_base_seconds} s")
                print(f"Single valid file found: {new_valid_file[0]}")
                setattr(self, "valid_files", new_valid_file)
                setattr(self, "unread_files", new_valid_file)
                print(f"New attributes "
                      f"'valid_files' and 'unread_files' set")
            else:
                raise ModelInputError(f"Single valid file not found for "
                                      f"valid time = {self.valid_time}")
                
    def read_file(self):
        """ Reads a single model output file using xarray"""
        if self.data_format == "netcdf":
            try:
                with xr.open_dataset(self.unread_files[0]) as ds: 
                    print(f"Netcdf file read sucessfully: "
                          f"{self.unread_files[0]}")
                    self.ds = ds # Save the entire dataset as an attribute   
                    self.unread_files.pop(0)
            except IOError as e:
                print("I/O error({0}): {1}".format(e.errno, e.strerror))
        elif self.data_format == "grib2":
            try:
                with xr.open_dataset(self.unread_files[0], 
                                     engine='pynio') as ds:
                    print(f"Grib file read sucessfully: "
                          f"{self.unread_files[0]}")
                    self.ds = ds # Save the entire dataset as an attribute   
                    self.unread_files.pop(0)
            except IOError as e:
                print("I/O error({0}): {1}".format(e.errno, e.strerror))
        
    def check_for_attributes(self, tmpval = "dims"):
        """Check for model attributes dims or coords set in 
            config.py and sets if any are missing
        
        Parameters
            ----------
            tmpval : str
                Either `dims` or `coords`
        """
        if not (tmpval == "dims" or tmpval == "coords"):
            raise ModelInputError(f"Attribute check can only"
                                  f" be for 'dims' or 'coords',"
                                  f" not {tmpval}")
    
        print(f"Checking {self.model_name} attributes")
        if not self.model_name in getattr(config, tmpval):
            print(f"No {tmpval} for {self.model_name}")
            return
        
        # If attribute missing, get and set attribute
        if not all([hasattr(self, k) for k \
                    in getattr(config, tmpval)[self.model_name]]):
            [print(f"Missing {tmpval}: {k}") for k in getattr(
                config, tmpval)[self.model_name] if not hasattr(self, k)]
            self.get_model_attributes(tmpval)
            
    def get_model_attributes(self, tmpval):
        """Gets model attributes if missing
        
        Parameters
            ----------
            tmpval : str
                Either `dims` or `coords`
        """       
        # For loop for simplicity since there are only 4 dimensions
        # max (time, x, y, z) and 4 coordinates max (time, x, y, z)
        for k,v in getattr(config, tmpval)[self.model_name].items():
            if not hasattr(self, k):
                tmpattr = getattr(self.ds, tmpval) \
                [getattr(config,tmpval)[self.model_name][k]]
                if hasattr(tmpattr, "values"):
                    print(f"Setting missing {tmpval} {k} to"
                          f"{type(tmpattr.values)}")
                    setattr(self, k, tmpattr.values)
                else:
                    print(f"Setting missing {tmpval} {k} to {tmpattr}")
                    setattr(self, k, tmpattr)
