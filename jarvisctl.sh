#!/usr/bin/env bash
# ===========================================================================
# JARVIS 服务管理脚本
# 支持启动、停止、重启、状态查看、日志查看等操作
# 自动管理后台服务进程的生命周期
# 兼容 bash 3.2+ (macOS 默认)
#
# 使用方式: ./jarvisctl.sh <command> [mode]
#
# 命令:
#   start   - 启动服务
#   stop    - 停止服务
#   restart - 重启服务
#   status  - 查看服务状态
#   logs    - 查看服务日志
#
# 模式 (仅 start/restart):
#   web        - FastAPI Web 服务 (端口 8011)
#   all        - 启动所有可后台运行的服务 (默认)
# ===========================================================================

set -euo pipefail

# ----- 配置 ----------------------------------------------------------------
PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
VENV_DIR="${PROJECT_DIR}/.venv"
MAIN_SCRIPT="${PROJECT_DIR}/run_jarvis.py"
LOG_DIR="${PROJECT_DIR}/data/logs"
PID_DIR="${PROJECT_DIR}/data/pids"

# 可后台运行的服务名
SERVICE_NAMES=("web")

service_port() {
	case "$1" in
		web)        echo "8011" ;;
		*)          echo "" ;;
	esac
}

service_desc() {
	case "$1" in
		web)        echo "FastAPI Web 服务" ;;
		active)     echo "主动运行模式" ;;
		cli)        echo "传统 CLI 模式" ;;
		demo)       echo "自动执行演示" ;;
		*)          echo "未知服务" ;;
	esac
}

service_args() {
	case "$1" in
		web)        echo "web --host 127.0.0.1 --port $(service_port web)" ;;
		active)     echo "active" ;;
		cli)        echo "cli" ;;
		demo)       echo "demo" ;;
		*)          echo "" ;;
	esac
}

# 判断是否可后台运行
is_background_service() {
	case "$1" in
		web) return 0 ;;
		*)   return 1 ;;
	esac
}

# 验证服务名是否合法
validate_service() {
	local args
	args="$(service_args "$1")"
	if [[ -z "$args" ]]; then
		echo "错误: 未知的服务模式 '$1'"
		echo "  可用模式: web active cli demo all"
		return 1
	fi
	return 0
}

# ----- 颜色 (使用 ANSI-C 引用，兼容 bash 3.2+) -----------------------------------------------
RED=$'\033[31m'
GREEN=$'\033[32m'
YELLOW=$'\033[33m'
CYAN=$'\033[36m'
BOLD=$'\033[1m'
NC=$'\033[0m'
# 检测不支持颜色的终端
case "${TERM:-dumb}" in
	dumb|"") RED=''; GREEN=''; YELLOW=''; CYAN=''; BOLD=''; NC='' ;;
esac

log_info()  { printf "${GREEN}[INFO]${NC}  %s\n" "$*"; }
log_warn()  { printf "${YELLOW}[WARN]${NC}  %s\n" "$*"; }
log_error() { printf "${RED}[ERROR]${NC} %s\n" "$*"; }
log_step()  { printf "\n${CYAN}══════════ %s ══════════${NC}\n" "$*"; }

# ----- 辅助函数 ------------------------------------------------------------

ensure_dirs() {
	mkdir -p "$LOG_DIR" "$PID_DIR"
}

pid_file() {
	echo "${PID_DIR}/${1}.pid"
}

log_file() {
	echo "${LOG_DIR}/${1}.log"
}

err_file() {
	echo "${LOG_DIR}/${1}.err"
}

# 获取服务 PID，不存在或进程已死返回空字符串
get_pid() {
	local service="$1"
	local pf
	pf="$(pid_file "$service")"
	local pid=""

	if [[ -f "$pf" ]]; then
		pid=$(cat "$pf" 2>/dev/null || true)
		if [[ -z "$pid" ]] || ! kill -0 "$pid" 2>/dev/null; then
			rm -f "$pf" 2>/dev/null || true
			pid=""
		fi
	fi
	echo "$pid"
}

# 日志轮转 (大于 10MB 时归档)
rotate_logs() {
	local service="$1"
	local f
	for f in "$(log_file "$service")" "$(err_file "$service")"; do
		if [[ -f "$f" ]]; then
			local size
			size=$(stat -f%z "$f" 2>/dev/null || stat -c%s "$f" 2>/dev/null || echo 0)
			if [[ "$size" -gt 10485760 ]]; then
				mv "$f" "${f}.1" 2>/dev/null || true
				rm -f "${f}.4" 2>/dev/null || true
				mv "${f}.3" "${f}.4" 2>/dev/null || true
				mv "${f}.2" "${f}.3" 2>/dev/null || true
			fi
		fi
	done
}

check_venv() {
	if [[ ! -d "$VENV_DIR" ]]; then
		log_error "虚拟环境不存在: ${VENV_DIR}"
		echo "  创建: python3 -m venv .venv"
		echo "  安装: source .venv/bin/activate && pip install -r src/requirements.txt"
		exit 1
	fi
}

cleanup_pid() {
	rm -f "$(pid_file "$1")" 2>/dev/null || true
}

# 检查端口是否被占用
check_port() {
	local port="$1"
	if command -v lsof &>/dev/null; then
		lsof -i :"$port" -P 2>/dev/null | grep -q LISTEN && return 0 || return 1
	elif command -v ss &>/dev/null; then
		ss -tln 2>/dev/null | grep -q ":${port} " && return 0 || return 1
	fi
	return 1
}

# ----- 服务生命周期 --------------------------------------------------------

# 启动单个服务
start_service() {
	local service="$1"

	if ! validate_service "$service"; then
		return 1
	fi

	# 检查是否已在运行
	local existing_pid
	existing_pid="$(get_pid "$service")"
	if [[ -n "$existing_pid" ]]; then
		log_warn "$(service_desc "$service") 已在运行 (PID: ${existing_pid})"
		return 0
	fi

	# 交互式模式只给提示
	if ! is_background_service "$service"; then
		log_info "$(service_desc "$service") 为交互式模式，请在终端手动运行:"
		echo "  source .venv/bin/activate && python3 run_jarvis.py $(service_args "$service")"
		return 0
	fi

	ensure_dirs
	rotate_logs "$service"

	log_info "正在启动 $(service_desc "$service")..."

	# 后台启动
	local pid
	nohup /bin/bash -c "
		source '${VENV_DIR}/bin/activate'
		cd '${PROJECT_DIR}'
		exec python3 '${MAIN_SCRIPT}' $(service_args "$service") \
			>> '$(log_file "$service")' \
			2>> '$(err_file "$service")'
	" >/dev/null 2>&1 &
	pid=$!
	echo "$pid" > "$(pid_file "$service")"

	# 等待端口就绪（最多 15 秒，嵌入模型加载较慢）
	local port
	port="$(service_port "$service")"
	local waited=0
	while [[ $waited -lt 15 ]]; do
		if ! kill -0 "$pid" 2>/dev/null; then
			break
		fi
		if [[ -z "$port" ]] || check_port "$port"; then
			break
		fi
		sleep 1
		waited=$((waited + 1))
	done

	if kill -0 "$pid" 2>/dev/null; then
		if [[ -n "$port" ]] && ! check_port "$port"; then
			log_warn "$(service_desc "$service") 进程运行中但端口 ${port} 未监听（等待 ${waited}s）"
		fi
		log_info "$(service_desc "$service") 启动成功 (PID: ${pid})"
	else
		log_error "$(service_desc "$service") 启动失败，请查看日志"
		echo "  日志: $(log_file "$service")"
		echo "  错误: $(err_file "$service")"
		cleanup_pid "$service"
		return 1
	fi
}

# 停止单个服务
stop_service() {
	local service="$1"

	if ! is_background_service "$service"; then
		log_info "$(service_desc "$service") 为交互式模式，请在终端按 Ctrl+C 停止"
		return 0
	fi

	local pid
	pid="$(get_pid "$service")"
	if [[ -z "$pid" ]]; then
		log_warn "$(service_desc "$service") 未在运行"
		return 0
	fi

	log_info "正在停止 $(service_desc "$service") (PID: ${pid})..."

	# SIGTERM -> 等待 -> SIGKILL
	kill -TERM "$pid" 2>/dev/null || true

	local waited=0
	while kill -0 "$pid" 2>/dev/null; do
		sleep 1
		waited=$((waited + 1))
		if [[ $waited -ge 5 ]]; then
			log_warn "未响应 SIGTERM，发送 SIGKILL..."
			kill -KILL "$pid" 2>/dev/null || true
			sleep 1
			break
		fi
	done

	if ! kill -0 "$pid" 2>/dev/null; then
		log_info "$(service_desc "$service") 已停止"
		cleanup_pid "$service"
	else
		log_error "无法停止 $(service_desc "$service")"
		return 1
	fi
}

# 显示单个服务状态
show_service_status() {
	local service="$1"
	local pid
	pid="$(get_pid "$service")"
	local port
	port="$(service_port "$service")"
	local port_status=""

	if [[ -n "$pid" ]] && [[ -n "$port" ]]; then
		if check_port "$port"; then
			port_status="${GREEN}●${NC} :${port}"
		else
			port_status="${YELLOW}○${NC} :${port} (未监听)"
		fi
	fi

	if [[ -n "$pid" ]]; then
		printf "  ${GREEN}●${NC} %-12s %s  running  PID: %-6s %s\n" \
			"${service}" "$(service_desc "$service")" "$pid" "$port_status"
	else
		printf "  ${RED}○${NC} %-12s %s  stopped\n" \
			"${service}" "$(service_desc "$service")"
	fi
}

# ----- 主命令 --------------------------------------------------------------

usage() {
	echo "JARVIS 服务管理脚本"
	echo ""
	echo "用法:"
	echo "  $(basename "$0") <command> [mode]"
	echo ""
	echo "命令:"
	echo "  start        启动服务"
	echo "  stop         停止服务"
	echo "  restart      重启服务"
	echo "  status       查看服务状态"
	echo "  logs         查看服务日志"
	echo "  help         显示此帮助"
	echo ""
	echo "模式 (仅 start/restart):"
	echo "  web          FastAPI Web 服务 (端口 $(service_port web))"
	echo "  all          启动所有可后台运行的服务 (默认)"
	echo ""
	echo "示例:"
	echo "  $(basename "$0") start              启动 Web 服务"
	echo "  $(basename "$0") start web          启动 FastAPI Web 服务"
	echo "  $(basename "$0") stop               停止服务"
	echo "  $(basename "$0") restart web        重启 Web 服务"
	echo "  $(basename "$0") status             查看服务状态"
	echo "  $(basename "$0") logs web           查看 Web 服务日志"
	echo "  $(basename "$0") logs web -f        实时跟踪日志"
}

# ===== 主逻辑 ==============================================================

main() {
	local command="${1:-help}"
	local service="${2:-all}"

	if [[ "$command" == "start" ]] || [[ "$command" == "restart" ]] || [[ "$command" == "stop" ]]; then
		check_venv
		ensure_dirs
	fi

	case "$command" in
		# ----- start ---------------------------------------------------
		start)
			log_step "JARVIS 服务启动"

			if [[ "$service" == "all" ]]; then
				local failed=0
				local s
				for s in "${SERVICE_NAMES[@]}"; do
					start_service "$s" || failed=$((failed + 1))
				done
				echo ""
				show_service_status "web"
				if [[ $failed -eq 0 ]]; then
					log_info "服务已启动"
				else
					log_warn "${failed} 个服务启动失败，请查看日志"
				fi
			else
				start_service "$service"
			fi
			;;

		# ----- stop ----------------------------------------------------
		stop)
			log_step "JARVIS 服务停止"

			if [[ "$service" == "all" ]]; then
				local i
				for ((i = ${#SERVICE_NAMES[@]} - 1; i >= 0; i--)); do
					stop_service "${SERVICE_NAMES[$i]}"
				done
				log_info "服务已停止"
			else
				stop_service "$service"
			fi
			;;

		# ----- restart -------------------------------------------------
		restart)
			log_step "JARVIS 服务重启"

			if [[ "$service" == "all" ]]; then
				local i
				for ((i = ${#SERVICE_NAMES[@]} - 1; i >= 0; i--)); do
					stop_service "${SERVICE_NAMES[$i]}"
				done
				echo ""
				local s
				for s in "${SERVICE_NAMES[@]}"; do
					start_service "$s"
				done
				echo ""
				show_service_status "web"
				log_info "服务已重启"
			else
				stop_service "$service"
				echo ""
				start_service "$service"
			fi
			;;

		# ----- status --------------------------------------------------
		status)
			log_step "JARVIS 服务状态"
			echo ""
			echo "  项目: JARVIS 智能体基座"
			echo "  目录: ${PROJECT_DIR}"
			echo ""

			local any_running=false
			local s
			for s in "${SERVICE_NAMES[@]}"; do
				show_service_status "$s"
				local pid
				pid="$(get_pid "$s")"
				[[ -n "$pid" ]] && any_running=true
			done

			echo ""
			if $any_running; then
				log_info "JARVIS 服务运行中"
				echo "  API 地址: http://127.0.0.1:$(service_port web)"
			else
				log_warn "JARVIS 服务未运行"
				echo "  使用 ./jarvisctl.sh start 启动"
			fi
			;;

		# ----- logs ----------------------------------------------------
		logs)
			local log_target="$service"
			local follow=""
			local n_val=50

			local arg2="${2:-}"
			local arg3="${3:-}"
			if [[ "$arg2" == "-f" ]] || [[ "$arg3" == "-f" ]]; then
				follow="-f"
			fi
			if [[ "$arg2" =~ ^-n[0-9]+$ ]]; then
				n_val="${arg2#-n}"
			elif [[ "$arg3" =~ ^-n[0-9]+$ ]]; then
				n_val="${arg3#-n}"
			fi

			if [[ "$log_target" == "all" ]] || [[ -z "$log_target" ]] || [[ "$log_target" == "status" ]]; then
				echo "JARVIS 日志文件:"
				local s
				for s in "${SERVICE_NAMES[@]}"; do
					local lf
					lf="$(log_file "$s")"
					if [[ -f "$lf" ]]; then
						echo "  [${s}] ${lf} ($(wc -l < "$lf" 2>/dev/null || echo 0) 行)"
					else
						echo "  [${s}] $(service_desc "$s") (暂无日志)"
					fi
				done
				echo ""
				echo "查看具体: ./jarvisctl.sh logs web"
				echo "实时跟踪: ./jarvisctl.sh logs web -f"
			else
				local lf
				lf="$(log_file "$log_target")"
				local ef
				ef="$(err_file "$log_target")"
				local desc
				desc="$(service_desc "$log_target")"

				if [[ ! -f "$lf" ]]; then
					log_warn "${desc} 暂无日志"
					exit 0
				fi

				echo "=== ${desc} ==="
				echo ""

				if [[ -n "$follow" ]]; then
					tail -f "$lf"
				else
					tail -n "$n_val" "$lf"
				fi

				if [[ -f "$ef" && -s "$ef" ]]; then
					echo ""
					echo "--- 错误 ---"
					tail -n 10 "$ef"
				fi
			fi
			;;

		# ----- help ----------------------------------------------------
		help|--help|-h)
			usage
			;;
		*)
			echo "错误: 未知命令 '${command}'"
			echo ""
			usage
			exit 1
			;;
	esac
}

main "$@"
