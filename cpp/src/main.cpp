#include <chrono>
#include <thread>
#include <sys/stat.h>
#include "yaml-cpp/yaml.h"
#include "Kinematics.h"
#include "Logger.h"
#include "DynamixelSDKWrapper.h"
#include "PigpioServo.h"
#include <cmath>
#include <iostream>
#ifndef M_PI
#  define M_PI 3.14159265358979323846
#endif

int main(){
    using namespace std::chrono;
    time_t last_mtime = 0;
    YAML::Node cfg;
    Logger logger;
    bool logging_on = false;
    int log_buffer_count = 0;
    const int LOG_FLUSH_INTERVAL = 20;

    DynamixelSDKWrapper tail("/dev/ttyUSB0", 57600, 1);
    PigpioServo fin(13);

    auto t0 = steady_clock::now();
    auto loop_dt = milliseconds(50);
    auto next_time = t0;

    while(true) {
        // 1) Wait until the next 50 ms boundary
        std::this_thread::sleep_until(next_time);

        // 2) Immediately schedule the next wakeup
        next_time += loop_dt;

        // 3) Timestamp for sin calculation
        double t = duration<double>(steady_clock::now() - t0).count();

        // reload config if changed
        struct stat st; stat("cfg.yaml", &st);
        if(st.st_mtime > last_mtime) {
            cfg = YAML::LoadFile("cfg.yaml");
            last_mtime = st.st_mtime;
        }
        std::string mode = cfg["mode"].as<std::string>("standby");

        double phi_tail=0, phi_fin=0;
        if(mode=="test"){
            phi_tail = cfg["phi_tail"].as<double>();
            phi_fin  = cfg["phi_fin" ].as<double>();
        } else if(mode=="symmetric_sin"){
            double A_t=cfg["amplitude_tail"].as<double>();
            double A_f=cfg["amplitude_fin" ].as<double>();
            double f  =cfg["frequency"     ].as<double>();
            double ph =cfg["phase"         ].as<double>();
            phi_tail = A_t*sin(2*M_PI*f*t);
            phi_fin  = A_f*sin(2*M_PI*f*t + ph);
        }
        double theta_tail = inverse_tail(phi_tail);
        double theta_fin  = fin_to_servo(phi_fin);

        // Temporary for empirical calibration :
        if (mode == "test"){
            double theta_tail = phi_tail;
            double theta_fin  = phi_fin;
        }

        tail.setPositionDeg(theta_tail);
        fin.setAngle(theta_fin);

        // manage logging
        bool want = cfg["logging"].as<bool>(false);
        if(want && !logging_on) { logger.openNewFile(); logging_on=true; }
        if(!want && logging_on) { logger.close(); logging_on=false;  log_buffer_count=0;}
        if(logging_on) {
            auto s = tail.readState();
            logger.bufferRow({
                std::to_string(t),
                std::to_string(phi_tail), std::to_string(theta_tail),
                std::to_string(phi_fin),  std::to_string(theta_fin),
                std::to_string(s.pos), std::to_string(s.current), std::to_string(s.voltage),
                mode
            });
            if (++log_buffer_count >= LOG_FLUSH_INTERVAL){
                logger.flush();
                log_buffer_count = 0;
            }
        }

    }
    return 0;
}