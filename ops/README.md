# Swarm Ops Scripts

- start_stage1_prod.sh: Start Production server (5050)
- start_stage2_uat.sh: Start UAT/Pre-prod server (5053)
- start_stage3_dev.sh: Start DEV server (5051)
- stage1.env, stage2.env, stage3.env: Environment configs for each stage

## Usage

1. Run the appropriate script to start the desired environment.
2. Each environment is isolated and can be managed independently.
3. Use the environment variables to configure Flask and other services.
